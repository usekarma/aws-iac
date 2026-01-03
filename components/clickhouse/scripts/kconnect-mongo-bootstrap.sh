#!/usr/bin/env bash
set -euo pipefail

echo "[kconnect-bootstrap] ============================"
echo "[kconnect-bootstrap] Starting Debezium Mongo bootstrap"
echo "[kconnect-bootstrap] ============================"

CONNECTOR_NAME="${CONNECTOR_NAME:-mongo-cdc-core}"
CONNECTOR_JSON_PATH="${CONNECTOR_JSON_PATH:-/usr/local/bin/${CONNECTOR_NAME}.json}"

KCONNECT_HOST="${KCONNECT_HOST:-}"
MONGO_CONNECTION_STRING="${MONGO_CONNECTION_STRING:-}"
CURL_BIN="${CURL_BIN:-curl}"
JQ_BIN="${JQ_BIN:-jq}"

echo "[kconnect-bootstrap] ===== ENVIRONMENT ====="
echo "CONNECTOR_NAME=${CONNECTOR_NAME}"
echo "KCONNECT_HOST=${KCONNECT_HOST}"
echo "MONGO_CONNECTION_STRING=${MONGO_CONNECTION_STRING}"
echo "CONNECTOR_JSON_PATH=${CONNECTOR_JSON_PATH}"
echo "CURL_BIN=${CURL_BIN}"
echo "JQ_BIN=${JQ_BIN}"
echo "============================================"

# ------------------------------------------------------------
# Guard rails: missing env → WARN + exit 0 (safe for userdata)
# ------------------------------------------------------------
if [[ -z "${MONGO_CONNECTION_STRING}" ]]; then
  echo "[kconnect-bootstrap] WARN: MONGO_CONNECTION_STRING is not set. Skipping connector bootstrap."
  exit 0
fi

if [[ -z "${KCONNECT_HOST}" ]]; then
  echo "[kconnect-bootstrap] WARN: KCONNECT_HOST is not set. Skipping connector bootstrap."
  exit 0
fi

if ! command -v "${JQ_BIN}" >/dev/null 2>&1; then
  echo "[kconnect-bootstrap] WARN: jq not found (JQ_BIN=${JQ_BIN}). Skipping connector bootstrap."
  exit 0
fi

# Normalize host (allow host:port or just host)
if [[ "${KCONNECT_HOST}" == *:* ]]; then
  KCONNECT_BASE="http://${KCONNECT_HOST}"
else
  KCONNECT_BASE="http://${KCONNECT_HOST}:8083"
fi

echo "[kconnect-bootstrap] Kafka Connect REST = ${KCONNECT_BASE}"

# ------------------------------------------------------------
# Write connector config JSON (name + config)
# ------------------------------------------------------------
echo "[kconnect-bootstrap] Writing Debezium config → ${CONNECTOR_JSON_PATH}"

cat >"${CONNECTOR_JSON_PATH}" <<EOF
{
  "name": "${CONNECTOR_NAME}",
  "config": {
    "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
    "tasks.max": "1",

    "mongodb.connection.string": "${MONGO_CONNECTION_STRING}",
    "mongodb.name": "mongo",

    "database.include.list": "sales,reports",
    "collection.include.list": "sales.customers,sales.vendors,sales.products,sales.inventory,sales.orders,reports.report_runs,reports.report_requests,reports.report_attempts,reports.dependency_calls,reports.outcomes",

    "topic.prefix": "mongo",
    "snapshot.mode": "initial",

    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "false"
  }
}
EOF

# ------------------------------------------------------------
# Wait for Kafka Connect (but never fail boot)
# ------------------------------------------------------------
echo "[kconnect-bootstrap] Waiting for Kafka Connect at ${KCONNECT_BASE}..."
for i in {1..60}; do
  if "${CURL_BIN}" -fsS "${KCONNECT_BASE}/connectors" >/dev/null 2>&1; then
    echo "[kconnect-bootstrap] Kafka Connect is up."
    break
  fi
  echo "[kconnect-bootstrap] Kafka Connect not ready yet (attempt ${i}/60); sleeping 5s..."
  sleep 5
  if [[ "${i}" -eq 60 ]]; then
    echo "[kconnect-bootstrap] WARN: Kafka Connect did not become ready in time. Skipping connector bootstrap."
    exit 0
  fi
done

# ------------------------------------------------------------
# Create connector via POST /connectors
#   - 201 Created => good
#   - 409 Exists  => update via PUT /config (true idempotency)
# ------------------------------------------------------------
echo "[kconnect-bootstrap] Applying Debezium Mongo connector ${CONNECTOR_NAME}..."

CREATE_CODE="$(
  "${CURL_BIN}" -sS -o "/tmp/${CONNECTOR_NAME}_create_resp.json" -w "%{http_code}" \
    -X POST "${KCONNECT_BASE}/connectors" \
    -H "Content-Type: application/json" \
    --data-binary "@${CONNECTOR_JSON_PATH}" || true
)"

echo "[kconnect-bootstrap] Connector POST HTTP status: ${CREATE_CODE}"
echo "[kconnect-bootstrap] Response body:"
cat "/tmp/${CONNECTOR_NAME}_create_resp.json" 2>/dev/null || echo "[kconnect-bootstrap] (no response body)"
echo

if [[ "${CREATE_CODE}" == "201" ]]; then
  echo "[kconnect-bootstrap] Connector created."
elif [[ "${CREATE_CODE}" == "409" ]]; then
  echo "[kconnect-bootstrap] Connector already exists; updating config via PUT ..."

  # Extract just the config object (Kafka Connect expects the config map, not {name, config})
  CONFIG_ONLY_PATH="/tmp/${CONNECTOR_NAME}_config_only.json"
  "${JQ_BIN}" -c '.config' "${CONNECTOR_JSON_PATH}" > "${CONFIG_ONLY_PATH}"

  UPDATE_CODE="$(
    "${CURL_BIN}" -sS -o "/tmp/${CONNECTOR_NAME}_update_resp.json" -w "%{http_code}" \
      -X PUT "${KCONNECT_BASE}/connectors/${CONNECTOR_NAME}/config" \
      -H "Content-Type: application/json" \
      --data-binary "@${CONFIG_ONLY_PATH}" || true
  )"

  echo "[kconnect-bootstrap] Connector PUT HTTP status: ${UPDATE_CODE}"
  echo "[kconnect-bootstrap] Update response body:"
  cat "/tmp/${CONNECTOR_NAME}_update_resp.json" 2>/dev/null || echo "[kconnect-bootstrap] (no response body)"
  echo

  if [[ "${UPDATE_CODE}" != "200" && "${UPDATE_CODE}" != "201" ]]; then
    echo "[kconnect-bootstrap] WARN: Unexpected HTTP status from connector update: ${UPDATE_CODE}"
  fi
else
  echo "[kconnect-bootstrap] WARN: Unexpected HTTP status from connector create: ${CREATE_CODE}"
fi

# ------------------------------------------------------------
# Status check (best-effort, never fatal)
# ------------------------------------------------------------
echo "[kconnect-bootstrap] Checking connector status for ${CONNECTOR_NAME}..."
for i in {1..30}; do
  STATUS_JSON="$("${CURL_BIN}" -sS "${KCONNECT_BASE}/connectors/${CONNECTOR_NAME}/status" || true)"

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
