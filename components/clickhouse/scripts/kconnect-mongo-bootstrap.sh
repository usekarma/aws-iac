#!/usr/bin/env bash
set -euo pipefail

CONNECTOR_JSON_PATH="/usr/local/bin/mongo-cdc-sales.json"
KCONNECT_HOST="${KCONNECT_HOST}"
MONGO_CONNECTION_STRING="${MONGO_CONNECTION_STRING}"

echo "[kconnect-bootstrap] Writing Debezium Mongo connector config to ${CONNECTOR_JSON_PATH}"

cat >"${CONNECTOR_JSON_PATH}" <<EOF
{
  "name": "mongo-cdc-sales",
  "config": {
    "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
    "tasks.max": "1",

    "mongodb.connection.string": "${MONGO_CONNECTION_STRING}",
    "mongodb.name": "mongo",

    "database.include.list": "sales",
    "collection.include.list": "sales.customers,sales.vendors,sales.products,sales.inventory,sales.orders",

    "topic.prefix": "mongo",
    "transforms": "route",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": ".*",
    "transforms.route.replacement": "mongo.sales.cdc",

    "snapshot.mode": "initial",

    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "false"
  }
}
EOF

if [[ -z "${KCONNECT_HOST}" ]]; then
  echo "[kconnect-bootstrap] KCONNECT_HOST not set; skipping connector bootstrap."
  exit 0
fi

echo "[kconnect-bootstrap] Waiting for Kafka Connect at ${KCONNECT_HOST}:8083..."
for i in {1..60}; do
  if curl -fsS "http://${KCONNECT_HOST}:8083/connectors" >/dev/null 2>&1; then
    echo "[kconnect-bootstrap] Kafka Connect is up."
    break
  fi
  sleep 5
done

echo "[kconnect-bootstrap] Applying Debezium Mongo connector mongo-cdc-sales..."
CREATE_RESP="$(curl -sS -X POST "http://${KCONNECT_HOST}:8083/connectors" \
  -H "Content-Type: application/json" \
  --data-binary "@${CONNECTOR_JSON_PATH}" || true)"

echo "${CREATE_RESP}"

# If it already exists, POST can return 409 with an error body – that's fine for idempotent bootstrap.
# We still go on to check status.

echo "[kconnect-bootstrap] Checking connector status..."
for i in {1..30}; do
  STATUS_JSON="$(curl -sS "http://${KCONNECT_HOST}:8083/connectors/mongo-cdc-sales/status" || true)"

  if [[ "${STATUS_JSON}" == *'"name":"mongo-cdc-sales"'* ]]; then
    echo "${STATUS_JSON}"
    echo "[kconnect-bootstrap] Connector mongo-cdc-sales status retrieved."
    exit 0
  fi

  echo "[kconnect-bootstrap] Connector status not ready yet (attempt ${i}/30); sleeping 5s..."
  sleep 5
done

echo "[kconnect-bootstrap] WARN: connector status still not available after retries"
exit 0
