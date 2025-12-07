#!/usr/bin/env bash
set -euo pipefail

echo "[kafka-ch-bootstrap] Starting Kafka → ClickHouse bootstrap..."

: "${REDPANDA_HOST:?REDPANDA_HOST is required}"
: "${CLICKHOUSE_BUCKET:?CLICKHOUSE_BUCKET is required}"
: "${CLICKHOUSE_PREFIX:?CLICKHOUSE_PREFIX is required}"

CLICKHOUSE_CLIENT="${CLICKHOUSE_CLIENT:-clickhouse-client}"
CLICKHOUSE_SCHEMA_DIR="${CLICKHOUSE_SCHEMA_DIR:-/usr/local/bin/schema_clickhouse}"
AWS_CLI="${AWS_CLI:-aws}"

# Normalize broker (allow host:port or just host)
if [[ "${REDPANDA_HOST}" == *:* ]]; then
  BROKER="${REDPANDA_HOST}"
else
  BROKER="${REDPANDA_HOST}:9092"
fi

echo "[kafka-ch-bootstrap] Using broker ${BROKER}"

# Ensure local schema dir exists
mkdir -p "${CLICKHOUSE_SCHEMA_DIR}"

SCHEMA_S3_BASE="s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema_clickhouse"
echo "[kafka-ch-bootstrap] Syncing schema from ${SCHEMA_S3_BASE} to ${CLICKHOUSE_SCHEMA_DIR}..."
"${AWS_CLI}" s3 sync "${SCHEMA_S3_BASE}/" "${CLICKHOUSE_SCHEMA_DIR}/"

RAW_SCHEMA_FILE="${CLICKHOUSE_SCHEMA_DIR}/00_raw_mongo_cdc.sql"

echo "[kafka-ch-bootstrap] DEBUG: listing schema dir:"
ls -l "${CLICKHOUSE_SCHEMA_DIR}" || true

if [[ ! -f "${RAW_SCHEMA_FILE}" ]]; then
  echo "[kafka-ch-bootstrap] ERROR: raw schema file not found: ${RAW_SCHEMA_FILE}"
  exit 1
fi

# --------------------------------------------------------------------
# Apply raw CDC schema (template {{KAFKA_BROKER}} → actual broker)
# --------------------------------------------------------------------
TMP_SQL="/tmp/00_raw_mongo_cdc_rendered.sql"
sed "s/{{KAFKA_BROKER}}/${BROKER}/g" "${RAW_SCHEMA_FILE}" > "${TMP_SQL}"

echo "[kafka-ch-bootstrap] Applying raw CDC schema from ${TMP_SQL}..."
"${CLICKHOUSE_CLIENT}" --multiquery < "${TMP_SQL}"
echo "[kafka-ch-bootstrap] Raw CDC schema applied successfully."

# --------------------------------------------------------------------
# Apply remaining schema files (domain + SLA), sorted by filename
# --------------------------------------------------------------------
echo "[kafka-ch-bootstrap] Applying domain and SLA schema from ${CLICKHOUSE_SCHEMA_DIR}..."

shopt -s nullglob
SCHEMA_FILES=( "${CLICKHOUSE_SCHEMA_DIR}"/[0-9][0-9]_*.sql )
shopt -u nullglob

if [[ ${#SCHEMA_FILES[@]} -eq 0 ]]; then
  echo "[kafka-ch-bootstrap] WARN: no numbered schema files found in ${CLICKHOUSE_SCHEMA_DIR}"
fi

for file in "${SCHEMA_FILES[@]}"; do
  # 00_raw_mongo_cdc.sql is already applied via TMP_SQL
  if [[ "${file}" == "${RAW_SCHEMA_FILE}" ]]; then
    continue
  fi

  base="$(basename "${file}")"
  echo "[kafka-ch-bootstrap] Applying ${base}..."
  sed "s/{{KAFKA_BROKER}}/${BROKER}/g" "${file}" \
    | "${CLICKHOUSE_CLIENT}" --multiquery
done

echo "[kafka-ch-bootstrap] ClickHouse CDC + schema bootstrap completed."
