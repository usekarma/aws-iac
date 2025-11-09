#!/usr/bin/env bash
set -euxo pipefail

# ================= Prometheus + Grafana + Exporters =================

# ---- Prometheus (binary install) ----
cd /opt
if [[ ! -d "/opt/prometheus-${PROMETHEUS_VER}.linux-amd64" ]]; then
  curl -fL -o /opt/prometheus.tgz \
    "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VER}/prometheus-${PROMETHEUS_VER}.linux-amd64.tar.gz"
  tar xzf /opt/prometheus.tgz
  rm -f /opt/prometheus.tgz
fi
ln -sf "/opt/prometheus-${PROMETHEUS_VER}.linux-amd64" /opt/prometheus

# System user
if ! id -u prometheus >/dev/null 2>&1; then
  if [[ "$PM" == "apt" ]]; then
    useradd --system --no-create-home --shell /usr/sbin/nologin prometheus || true
  else
    useradd --system --no-create-home --shell /sbin/nologin prometheus || true
  fi
fi

install -d -o prometheus -g prometheus /var/lib/prometheus /etc/prometheus

cat >/etc/prometheus/prometheus.yml <<'YAML'
global:
  scrape_interval: 15s

scrape_configs:
  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['127.0.0.1:9090']

  # Local node_exporter (this Prom box)
  - job_name: 'node-local'
    static_configs:
      - targets: ['127.0.0.1:9100']
        labels: { role: 'prom-box' }

  # Remote node_exporters (Mongo & Redpanda boxes)
  - job_name: 'node-remote'
    static_configs:
      - targets:
          - "${MONGO_HOST}:${MONGO_NODE_PORT}"
          - "${REDPANDA_HOST}:${REDPANDA_NODE_PORT}"
        labels: { role: 'remote-node' }

  # ClickHouse native metrics on this host
  - job_name: 'clickhouse'
    metrics_path: /metrics
    static_configs:
      - targets: ['127.0.0.1:9363']

  # MongoDB exporter (on Mongo box)
  - job_name: 'mongo'
    metrics_path: /metrics
    static_configs:
      - targets:
          - "${MONGO_HOST}:${MONGO_EXP_PORT}"
        labels: { service: 'mongodb' }

  # Redpanda admin/metrics (on Redpanda box)
  - job_name: 'redpanda'
    metrics_path: /metrics
    static_configs:
      - targets:
          - "${REDPANDA_HOST}:${REDPANDA_EXP_PORT}"
        labels: { service: 'redpanda-admin' }

  # Kafka Connect
  - job_name: 'kconnect'
    metrics_path: /metrics
    static_configs:
      - targets:
          - 'kconnect-metrics.internal:9404'
        labels: { service: 'kconnect' }

YAML

cat >/etc/systemd/system/prometheus.service <<'EOF'
[Unit]
Description=Prometheus
After=network-online.target
Wants=network-online.target
[Service]
User=prometheus
Group=prometheus
ExecStart=/opt/prometheus/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.listen-address=0.0.0.0:9090
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
systemctl daemon-reload
systemctl enable --now prometheus

# ---- Grafana (repo install) ----
if [[ "$PM" == "apt" ]]; then
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://packages.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana.gpg
  echo "deb [signed-by=/usr/share/keyrings/grafana.gpg] https://packages.grafana.com/oss/deb stable main" \
    > /etc/apt/sources.list.d/grafana.list
  apt-get update -y
  apt-get install -y grafana
else
  if [[ ! -f /etc/yum.repos.d/grafana.repo ]]; then
    cat >/etc/yum.repos.d/grafana.repo <<'REPO'
[grafana]
name=Grafana OSS
baseurl=https://packages.grafana.com/oss/rpm
repo_gpgcheck=1
enabled=1
gpgcheck=1
gpgkey=https://packages.grafana.com/gpg.key
REPO
  fi
  $PM -y makecache || true
  $PM -y install grafana
fi
systemctl enable --now grafana-server


# ---- Node Exporter (binary install; loopback only) ----
cd /opt
if [[ ! -d "/opt/node_exporter-${NODEEXP_VER}.linux-amd64" ]]; then
  curl -fL -o /opt/node_exporter.tgz \
    "https://github.com/prometheus/node_exporter/releases/download/v${NODEEXP_VER}/node_exporter-${NODEEXP_VER}.linux-amd64.tar.gz"
  tar xzf /opt/node_exporter.tgz
  rm -f /opt/node_exporter.tgz
fi
ln -sf "/opt/node_exporter-${NODEEXP_VER}.linux-amd64" /opt/node_exporter

if ! id -u nodeexp >/dev/null 2>&1; then
  if [[ "$PM" == "apt" ]]; then
    useradd --system --no-create-home --shell /usr/sbin/nologin nodeexp || true
  else
    useradd --system --no-create-home --shell /sbin/nologin nodeexp || true
  fi
fi

cat >/etc/systemd/system/node_exporter.service <<'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target
[Service]
User=nodeexps
Group=nodeexp
ExecStart=/opt/node_exporter/node_exporter --web.listen-address=127.0.0.1:9100
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter

# ---- ClickHouse native Prometheus endpoint on 9363 ----
cat >/etc/clickhouse-server/config.d/40-prometheus.xml <<'EOF'
<clickhouse>
  <prometheus>
    <endpoint>/metrics</endpoint>
    <port>9363</port>
    <metrics>true</metrics>
    <events>true</events>
    <asynchronous_metrics>true</asynchronous_metrics>
  </prometheus>
</clickhouse>
EOF

systemctl restart clickhouse-server || true

# ---------- Optional: run Kafka Connect bootstrap script from S3 ----------

if [[ -n "${KCONNECT_HOST}" && -n "${MONGO_CONNECTION_STRING}" ]]; then
  echo "[userdata] Fetching Kafka Connect bootstrap script..."
  aws s3 cp "s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/scripts/kconnect-mongo-bootstrap.sh" /root/kconnect-mongo-bootstrap.sh || {
    echo "[userdata] WARN: could not fetch kconnect-mongo-bootstrap.sh from S3"
  }
  if [[ -s /root/kconnect-mongo-bootstrap.sh ]]; then
    chmod +x /root/kconnect-mongo-bootstrap.sh || true
    echo "[userdata] Running Kafka Connect bootstrap..."
    KCONNECT_HOST="${KCONNECT_HOST}" \
    MONGO_CONNECTION_STRING="${MONGO_CONNECTION_STRING}" \
      /root/kconnect-mongo-bootstrap.sh || echo "[userdata] WARN: kconnect bootstrap failed (non-fatal)"
  else
    echo "[userdata] WARN: kconnect bootstrap script missing or empty; skipping."
  fi
else
  echo "[userdata] KCONNECT_HOST or MONGO_CONNECTION_STRING not set; skipping Kafka Connect bootstrap."
fi

echo "[userdata] downloading Kafka→ClickHouse bootstrap script from S3..."
aws s3 cp "s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/scripts/kafka-clickhouse-bootstrap.sh" /usr/local/bin/kafka-clickhouse-bootstrap.sh

chmod +x /usr/local/bin/kafka-clickhouse-bootstrap.sh

echo "[userdata] running Kafka→ClickHouse bootstrap (REDPANDA_HOST=${REDPANDA_HOST})..."
/usr/local/bin/kafka-clickhouse-bootstrap.sh > /var/log/kafka_clickhouse_bootstrap.log 2>&1 || {
  echo "[userdata] Kafka→ClickHouse bootstrap failed — check /var/log/kafka_clickhouse_bootstrap.log"
  exit 1
}

echo "[userdata] Kafka→ClickHouse bootstrap completed successfully."
echo "[userdata] downloading Grafana bootstrap script..."
aws s3 cp "s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/scripts/grafana-bootstrap.sh" /usr/local/bin/grafana-bootstrap.sh

chmod +x /usr/local/bin/grafana-bootstrap.sh

echo "[userdata] running Grafana bootstrap..."
/usr/local/bin/grafana-bootstrap.sh > /var/log/grafana_bootstrap.log 2>&1 || {
  echo "[userdata] Grafana bootstrap failed, see /var/log/grafana_bootstrap.log"
  exit 1
}

echo "[userdata] Grafana bootstrap completed successfully."
