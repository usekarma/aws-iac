#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------------------
# Debezium MongoDB CDC bootstrap
#
# Goals:
#   - Single "core" connector for multiple Mongo DBs (sales + reports)
#   - Per-collection topics (Debezium defaults), e.g.:
#       mongo.sales.orders
#       mongo.sales.customers
#       mongo.reports.report_runs
#   - Idempotent and safe to re-run
#
# Required env:
#   - KCONNECT_HOST              (host or host:port for Kafka Connect, port defaults to 8083)
#   - MONGO_CONNECTION_STRING    (standard Mongo connection string)
#
# Optional env:
#   - CONNECTOR_NAME             (default: mongo-cdc-core)
#   - CONNECTOR_JSON_PATH        (default: /usr/local/bin/mongo-cdc-core.json)
# --------------------------------------------------------------------

CONNECTOR_NAME="${CONNECTOR_NAME:-mongo-cdc-core}"
CONNECTOR_JSON_PATH="${CONNECTOR_JSON_PATH:-/usr/local/bin/${CONNECTOR_NAME}.json}"

KCONNECT_HOST="${KCONNECT_HOST:-}"
MONGO_CONNECTION_STRING="${MONGO_CONNECTION_STRING:-}"

if [[ -z "${MONGO_CONNECTION_STRING}" ]]; then
  echo "[kconnect-bootstrap] ERROR: MONGO_CONNECTION_STRING is not set."
  exit 1
fi

if [[ -z "${KCONNECT_HOST}" ]]; then
  echo "[kconnect-bootstrap] KCONNECT_HOST not set; skipping connector bootstrap."
  exit 0
fi

# Normalize host (allow host:port or just host)
if [[ "${KCONNECT_HOST}" == *:* ]]; then
  KCONNECT_BASE="http://${KCONNECT_HOST}"
else
  KCONNECT_BASE="http://${KCONNECT_HOST}:8083"
fi

echo "[kconnect-bootstrap] Writing Debezium Mongo connector config to ${CONNECTOR_JSON_PATH}"

# Notes about the config we write:
#   - database.include.list: "sales,reports"
#   - collection.include.list: sales.* + reports.report_runs
#   - topic.prefix: "mongo" (Debezium default per-collection topics)
#   - snapshot.mode: "initial" to backfill existing data on first run
cat >"${CONNECTOR_JSON_PATH}" <<EOF
{
  "name": "${CONNECTOR_NAME}",
  "config": {
    "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
    "tasks.max": "1",

    "mongodb.connection.string": "${MONGO_CONNECTION_STRING}",
    "mongodb.name": "mongo",

    "database.include.list": "sales,reports",
    "collection.include.list": "sales.customers,sales.vendors,sales.products,sales.inventory,sales.orders,reports.report_runs",

    "topic.prefix": "mongo",
    "snapshot.mode": "initial",

    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "false"
  }
}
EOF

echo "[kconnect-bootstrap] Waiting for Kafka Connect at ${KCONNECT_BASE}..."
for i in {1..60}; do
  if curl -fsS "${KCONNECT_BASE}/connectors" >/dev/null 2>&1; then
    echo "[kconnect-bootstrap] Kafka Connect is up."
    break
  fi
  echo "[kconnect-bootstrap] Kafka Connect not ready yet (attempt ${i}/60); sleeping 5s..."
  sleep 5
  if [[ "${i}" -eq 60 ]]; then
    echo "[kconnect-bootstrap] ERROR: Kafka Connect did not become ready in time."
    exit 1
  fi
done

# --------------------------------------------------------------------
# Idempotent upsert:
#   - If connector exists, PUT to /config updates it.
#   - If it doesn't exist, PUT creates it.
# --------------------------------------------------------------------
echo "[kconnect-bootstrap] Applying Debezium Mongo connector ${CONNECTOR_NAME}..."

PUT_URL="${KCONNECT_BASE}/connectors/${CONNECTOR_NAME}/config"
RESP_BODY="/tmp/${CONNECTOR_NAME}_resp.json"

CREATE_OR_UPDATE_RESP="$(curl -sS -o "${RESP_BODY}" -w "%{http_code}" \
  -X PUT "${PUT_URL}" \
  -H "Content-Type: application/json" \
  --data-binary "@${CONNECTOR_JSON_PATH}" || true)"

HTTP_CODE="${CREATE_OR_UPDATE_RESP}"

echo "[kconnect-bootstrap] Connector PUT HTTP status: ${HTTP_CODE}"
echo "[kconnect-bootstrap] Response body:"
cat "${RESP_BODY}" || true
echo

if [[ -z "${HTTP_CODE}" || "${HTTP_CODE}" -lt 200 || "${HTTP_CODE}" -ge 300 ]]; then
  echo "[kconnect-bootstrap] WARN: non-2xx from connector PUT; continuing to status check."
fi

echo "[kconnect-bootstrap] Checking connector status for ${CONNECTOR_NAME}..."
for i in {1..30}; do
  STATUS_JSON="$(curl -sS "${KCONNECT_BASE}/connectors/${CONNECTOR_NAME}/status" || true)"

  if [[ "${STATUS_JSON}" == *"\"name\":\"${CONNECTOR_NAME}\""* ]]; then
    echo "${STATUS_JSON}"
    echo "[kconnect-bootstrap] Connector ${CONNECTOR_NAME} status retrieved."
    exit 0
  fi

  echo "[kconnect-bootstrap] Connector status not ready yet (attempt ${i}/30); sleeping 5s..."
  sleep 5
done

echo "[kconnect-bootstrap] WARN: connector status still not available after retries"
exit 0
