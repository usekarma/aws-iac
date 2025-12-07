#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------------------
# Kafka → ClickHouse CDC bootstrap
#
# Responsibilities:
#   - Resolve REDPANDA_HOST → broker (host:port)
#   - Sync ClickHouse schema files from S3 into a local schema dir
#   - Apply raw CDC schema (00_raw_mongo_cdc.sql) with kafka_broker_list param
#   - Apply all remaining schema files (NN_*.sql) in order
#
# Required env:
#   - REDPANDA_HOST               (host or host:port for Redpanda/Kafka)
#   - CLICKHOUSE_BUCKET
#   - CLICKHOUSE_PREFIX
#
# Optional env:
#   - CLICKHOUSE_CLIENT           (default: clickhouse-client)
#   - CLICKHOUSE_SCHEMA_DIR       (default: /opt/clickhouse-schema/schema)
# --------------------------------------------------------------------

REDPANDA_HOST="${REDPANDA_HOST:-}"
CLICKHOUSE_CLIENT="${CLICKHOUSE_CLIENT:-clickhouse-client}"
CLICKHOUSE_SCHEMA_DIR="${CLICKHOUSE_SCHEMA_DIR:-/opt/clickhouse-schema/schema}"

: "${CLICKHOUSE_BUCKET:?CLICKHOUSE_BUCKET is required}"
: "${CLICKHOUSE_PREFIX:?CLICKHOUSE_PREFIX is required}"

if [[ -z "${REDPANDA_HOST}" ]]; then
  echo "[kafka-ch-bootstrap] ERROR: REDPANDA_HOST is not set."
  exit 1
fi

# Normalize broker (allow host:port or just host)
if [[ "${REDPANDA_HOST}" == *:* ]]; then
  BROKER="${REDPANDA_HOST}"
else
  BROKER="${REDPANDA_HOST}:9092"
fi

SCHEMA_S3_BASE="s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema"

echo "[kafka-ch-bootstrap] Using broker ${BROKER}"
echo "[kafka-ch-bootstrap] Syncing schema from ${SCHEMA_S3_BASE} to ${CLICKHOUSE_SCHEMA_DIR}..."

mkdir -p "${CLICKHOUSE_SCHEMA_DIR}"

# Pull schema files from S3; requires awscli on the instance
aws s3 sync "${SCHEMA_S3_BASE}/" "${CLICKHOUSE_SCHEMA_DIR}/"

RAW_SCHEMA_FILE="${CLICKHOUSE_SCHEMA_DIR}/00_raw_mongo_cdc.sql"

if [[ ! -f "${RAW_SCHEMA_FILE}" ]]; then
  echo "[kafka-ch-bootstrap] ERROR: raw schema file not found after sync: ${RAW_SCHEMA_FILE}"
  exit 1
fi

echo "[kafka-ch-bootstrap] Applying raw CDC schema from ${RAW_SCHEMA_FILE}..."

# Apply raw CDC schema with broker param
"${CLICKHOUSE_CLIENT}" \
  --param kafka_broker_list="${BROKER}" \
  --multiquery < "${RAW_SCHEMA_FILE}"

echo "[kafka-ch-bootstrap] Raw CDC tables and MV are in place."

# --------------------------------------------------------------------
# Apply remaining schema files (domain + SLA) from schema dir
# --------------------------------------------------------------------
echo "[kafka-ch-bootstrap] Applying domain and SLA schema from ${CLICKHOUSE_SCHEMA_DIR}..."

shopt -s nullglob
SCHEMA_FILES=( "${CLICKHOUSE_SCHEMA_DIR}"/[0-9][0-9]_*.sql )
shopt -u nullglob

if [[ ${#SCHEMA_FILES[@]} -eq 0 ]]; then
  echo "[kafka-ch-bootstrap] WARN: no numbered schema files found in ${CLICKHOUSE_SCHEMA_DIR}"
fi

for file in "${SCHEMA_FILES[@]}"; do
  # Skip the raw file we already applied
  if [[ "${file}" == "${RAW_SCHEMA_FILE}" ]]; then
    continue
  fi
  echo "[kafka-ch-bootstrap] Applying ${file}..."
  "${CLICKHOUSE_CLIENT}" --multiquery < "${file}"
done

echo "[kafka-ch-bootstrap] ClickHouse CDC + schema bootstrap completed."
