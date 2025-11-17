#!/usr/bin/env bash
set -euxo pipefail

echo "[bootstrap] Starting Prometheus/Grafana wiring..."

# Expected env from userdata:
#   CLICKHOUSE_BUCKET
#   CLICKHOUSE_PREFIX
#   MONGO_HOST, MONGO_EXP_PORT, MONGO_NODE_PORT
#   REDPANDA_HOST, REDPANDA_EXP_PORT, REDPANDA_NODE_PORT
#   KCONNECT_HOST

: "${CLICKHOUSE_BUCKET:?CLICKHOUSE_BUCKET is required}"
: "${CLICKHOUSE_PREFIX:?CLICKHOUSE_PREFIX is required}"

# Prometheus config: local + remote targets
cat >/etc/prometheus/prometheus.yml <<EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['127.0.0.1:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['127.0.0.1:9100']

  - job_name: 'clickhouse'
    static_configs:
      - targets: ['127.0.0.1:9363']

  - job_name: 'mongo-exporter'
    static_configs:
      - targets: ['${MONGO_HOST:-127.0.0.1}:${MONGO_EXP_PORT:-9216}']

  - job_name: 'mongo-node'
    static_configs:
      - targets: ['${MONGO_HOST:-127.0.0.1}:${MONGO_NODE_PORT:-9100}']

  - job_name: 'redpanda-exporter'
    static_configs:
      - targets: ['${REDPANDA_HOST:-127.0.0.1}:${REDPANDA_EXP_PORT:-9644}']

  - job_name: 'redpanda-node'
    static_configs:
      - targets: ['${REDPANDA_HOST:-127.0.0.1}:${REDPANDA_NODE_PORT:-9100}']

  - job_name: 'kafka-connect'
    static_configs:
      - targets: ['${KCONNECT_HOST:-kconnect.svc.usekarma.local}:8083']
EOF

chown prometheus:prometheus /etc/prometheus/prometheus.yml || true
systemctl restart prometheus || true
echo "[bootstrap] Prometheus config written and service restarted."

# -------------------------------------------------------
# Download & run Kafka / ClickHouse wiring scripts
# -------------------------------------------------------
echo "[bootstrap] Downloading kconnect-mongo-bootstrap.sh..."
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/scripts/kconnect-mongo-bootstrap.sh" \
  /root/kconnect-mongo-bootstrap.sh
chmod +x /root/kconnect-mongo-bootstrap.sh

echo "[bootstrap] Downloading kafka-clickhouse-bootstrap.sh..."
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/scripts/kafka-clickhouse-bootstrap.sh" \
  /root/kafka-clickhouse-bootstrap.sh
chmod +x /root/kafka-clickhouse-bootstrap.sh

echo "[bootstrap] Downloading clickhouse-schema-views.sh..."
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/scripts/clickhouse-schema-views.sh" \
  /usr/local/bin/clickhouse-schema-views.sh
chmod +x /usr/local/bin/clickhouse-schema-views.sh

echo "[bootstrap] Running kconnect-mongo-bootstrap.sh..."
/root/kconnect-mongo-bootstrap.sh > /var/log/kconnect_mongo_bootstrap.log 2>&1 || {
  echo "[bootstrap] kconnect-mongo-bootstrap.sh failed — see /var/log/kconnect_mongo_bootstrap.log"
  exit 1
}

echo "[bootstrap] Running kafka-clickhouse-bootstrap.sh..."
/root/kafka-clickhouse-bootstrap.sh > /var/log/kafka_clickhouse_bootstrap.log 2>&1 || {
  echo "[bootstrap] kafka-clickhouse-bootstrap.sh failed — see /var/log/kafka_clickhouse_bootstrap.log"
  exit 1
}

echo "[bootstrap] Running clickhouse-schema-views.sh..."
/usr/local/bin/clickhouse-schema-views.sh > /var/log/clickhouse_schema_views.log 2>&1 || {
  echo "[bootstrap] clickhouse-schema-views.sh failed — see /var/log/clickhouse_schema_views.log"
  exit 1
}

# -------------------------------------------------------
# Grafana bootstrap (dashboards, datasources, etc.)
# -------------------------------------------------------
echo "[bootstrap] Downloading Grafana bootstrap script..."
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/scripts/grafana-bootstrap.sh" \
  /usr/local/bin/grafana-bootstrap.sh
chmod +x /usr/local/bin/grafana-bootstrap.sh

echo "[bootstrap] Running Grafana bootstrap..."
/usr/local/bin/grafana-bootstrap.sh > /var/log/grafana_bootstrap.log 2>&1 || {
  echo "[bootstrap] Grafana bootstrap failed — see /var/log/grafana_bootstrap.log"
  exit 1
}

echo "[bootstrap] Prometheus/Grafana wiring completed successfully."
