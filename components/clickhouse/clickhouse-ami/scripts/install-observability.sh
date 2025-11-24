#!/usr/bin/env bash
set -euxo pipefail

echo "[ami-obs] Starting observability install..."

# -------------------------------
# sudo helper (Packer runs as ec2-user)
# -------------------------------
SUDO="sudo"
if [[ "$(id -u)" -eq 0 ]]; then
  $SUDO=""
fi

# -------------------------------
# Package manager detection
# -------------------------------
PM=""
if command -v dnf >/dev/null 2>&1; then
  PM="dnf"
elif command -v yum >/dev/null 2>&1; then
  PM="yum"
elif command -v apt-get >/dev/null 2>&1; then
  PM="apt"
else
  echo "[ami-obs] ERROR: No supported package manager (dnf/yum/apt)" >&2
  exit 1
fi

# -------------------------------
# Base packages
# -------------------------------
if [[ "$PM" == "apt" ]]; then
  $SUDO apt-get update -y || true
  $SUDO apt-get install -y ca-certificates curl tar gzip xz-utils jq || true
else
  $SUDO $PM -y update || true
  $SUDO $PM -y install ca-certificates curl tar gzip xz jq --skip-broken || true
fi

# -------------------------------
# Versions (empty = latest)
# -------------------------------
PROMETHEUS_VER="${PROMETHEUS_VER:-}"
NODEEXP_VER="${NODEEXP_VER:-}"
GRAFANA_VER="${GRAFANA_VER:-}"

echo "[ami-obs] PROMETHEUS_VER='${PROMETHEUS_VER:-latest}', NODEEXP_VER='${NODEEXP_VER:-latest}', GRAFANA_VER='${GRAFANA_VER:-latest}'"

# =====================================================================================
# Prometheus (binary install + systemd)
# =====================================================================================

# Resolve Prometheus version if not pinned
if [[ -z "${PROMETHEUS_VER}" ]]; then
  echo "[ami-obs] Resolving latest Prometheus version from GitHub..."
  PROMETHEUS_VER="$(
    curl -fsSL https://api.github.com/repos/prometheus/prometheus/releases/latest \
    | jq -r '.tag_name' \
    | sed 's/^v//'
  )"
  if [[ -z "${PROMETHEUS_VER}" || "${PROMETHEUS_VER}" == "null" ]]; then
    echo "[ami-obs] WARNING: Could not resolve latest Prometheus version, falling back to 2.53.1"
    PROMETHEUS_VER="2.53.1"
  fi
fi

PROM_TARBALL_URL="https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VER}/prometheus-${PROMETHEUS_VER}.linux-amd64.tar.gz"
PROM_DIR="/opt/prometheus-${PROMETHEUS_VER}.linux-amd64"

echo "[ami-obs] Installing Prometheus ${PROMETHEUS_VER} from ${PROM_TARBALL_URL}..."

if [[ ! -d "${PROM_DIR}" ]]; then
  $SUDO mkdir -p /opt
  $SUDO curl -fL -o /tmp/prometheus.tgz "${PROM_TARBALL_URL}"
  $SUDO tar xzf /tmp/prometheus.tgz -C /opt
  $SUDO rm -f /tmp/prometheus.tgz
fi

$SUDO ln -sfn "${PROM_DIR}" /opt/prometheus

# Prometheus user + dirs
if ! id -u prometheus >/dev/null 2>&1; then
  $SUDO useradd --system --no-create-home --shell /usr/sbin/nologin prometheus || true
fi

$SUDO mkdir -p /etc/prometheus /var/lib/prometheus
$SUDO chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus

# Prometheus config
$SUDO tee /etc/prometheus/prometheus.yml >/dev/null <<'EOF'
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
EOF

$SUDO chown prometheus:prometheus /etc/prometheus/prometheus.yml

# Prometheus systemd unit
$SUDO tee /etc/systemd/system/prometheus.service >/dev/null <<'EOF'
[Unit]
Description=Prometheus
After=network-online.target
Wants=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/opt/prometheus/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.listen-address=0.0.0.0:9090
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# =====================================================================================
# Grafana (RPM/DEB repo + service, version-aware)
# =====================================================================================
echo "[ami-obs] Installing Grafana..."

if [[ "$PM" == "apt" ]]; then
  # Minimal Debian/Ubuntu-style install if you ever use it there
  $SUDO apt-get install -y adduser libfontconfig1 musl || true
  if [[ ! -f /etc/apt/sources.list.d/grafana.list ]]; then
    $SUDO tee /etc/apt/sources.list.d/grafana.list >/dev/null <<'EOF'
deb https://packages.grafana.com/oss/deb stable main
EOF
    $SUDO apt-get update -y || true
  fi

  if [[ -n "${GRAFANA_VER}" ]]; then
    echo "[ami-obs] Installing pinned Grafana ${GRAFANA_VER} (apt)..."
    # apt uses package=version syntax
    $SUDO apt-get install -y "grafana=${GRAFANA_VER}" || {
      echo "[ami-obs] WARNING: Grafana version '${GRAFANA_VER}' not found, falling back to latest..."
      $SUDO apt-get install -y grafana || true
    }
  else
    echo "[ami-obs] Installing latest Grafana (apt)..."
    $SUDO apt-get install -y grafana || true
  fi
else
  # RHEL/Amazon Linux style
  if [[ ! -f /etc/yum.repos.d/grafana.repo ]]; then
    $SUDO tee /etc/yum.repos.d/grafana.repo >/dev/null <<'EOF'
[grafana]
name=Grafana OSS
baseurl=https://packages.grafana.com/oss/rpm
repo_gpgcheck=1
enabled=1
gpgcheck=1
gpgkey=https://packages.grafana.com/gpg.key
sslverify=1
sslcacert=/etc/pki/tls/certs/ca-bundle.crt
EOF
  fi

  $SUDO $PM -y makecache || true

  if [[ -n "${GRAFANA_VER}" ]]; then
    echo "[ami-obs] Installing pinned Grafana ${GRAFANA_VER} (${PM})..."
    if ! $SUDO $PM -y install "grafana-${GRAFANA_VER}"; then
      echo "[ami-obs] WARNING: Grafana version '${GRAFANA_VER}' not found, falling back to latest..."
      $SUDO $PM -y install grafana || true
    fi
  else
    echo "[ami-obs] Installing latest Grafana (${PM})..."
    $SUDO $PM -y install grafana || true
  fi
fi

$SUDO systemctl daemon-reload || true
$SUDO systemctl enable --now grafana-server || true
echo "[ami-obs] Grafana installed and (attempted) started."

# ============================
# Grafana auth config: no login form, anonymous via ALB+SSO
# ============================
GRAFANA_INI="/etc/grafana/grafana.ini"

$SUDO tee "$GRAFANA_INI" >/dev/null <<'EOF'
[server]
# ALB terminates SSL/host; this keeps Grafana happy for redirects
root_url = %(protocol)s://%(domain)s/

[auth]
# Hide the native login form; rely on ALB + Cognito instead
disable_login_form = true
signout_redirect_url = /logout

[auth.anonymous]
enabled = true
org_role = Admin

[security]
admin_user = admin
admin_password = admin
EOF

$SUDO chown grafana:grafana "$GRAFANA_INI" || true
$SUDO systemctl restart grafana-server || true
echo "[ami-obs] Grafana configured for anonymous auth + external /logout."

# =====================================================================================
# Node Exporter (binary install + systemd)
# =====================================================================================

# Resolve node_exporter version if not pinned
if [[ -z "${NODEEXP_VER}" ]]; then
  echo "[ami-obs] Resolving latest node_exporter version from GitHub..."
  NODEEXP_VER="$(
    curl -fsSL https://api.github.com/repos/prometheus/node_exporter/releases/latest \
    | jq -r '.tag_name' \
    | sed 's/^v//'
  )"
  if [[ -z "${NODEEXP_VER}" || "${NODEEXP_VER}" == "null" ]]; then
    echo "[ami-obs] WARNING: Could not resolve latest node_exporter version, falling back to 1.8.1"
    NODEEXP_VER="1.8.1"
  fi
fi

NODE_TARBALL_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODEEXP_VER}/node_exporter-${NODEEXP_VER}.linux-amd64.tar.gz"
NODE_DIR="/opt/node_exporter-${NODEEXP_VER}.linux-amd64"

echo "[ami-obs] Installing node_exporter ${NODEEXP_VER} from ${NODE_TARBALL_URL}..."

if [[ ! -d "${NODE_DIR}" ]]; then
  $SUDO mkdir -p /opt
  $SUDO curl -fL -o /tmp/node_exporter.tgz "${NODE_TARBALL_URL}"
  $SUDO tar xzf /tmp/node_exporter.tgz -C /opt
  $SUDO rm -f /tmp/node_exporter.tgz
fi

$SUDO ln -sfn "${NODE_DIR}" /opt/node_exporter

if ! id -u nodeexp >/dev/null 2>&1; then
  $SUDO useradd --system --no-create-home --shell /usr/sbin/nologin nodeexp || true
fi

$SUDO tee /etc/systemd/system/node_exporter.service >/dev/null <<'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=nodeexp
Group=nodeexp
Type=simple
ExecStart=/opt/node_exporter/node_exporter --web.listen-address=127.0.0.1:9100
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload || true
$SUDO systemctl enable --now node_exporter || true

# =====================================================================================
# ClickHouse: enable Prometheus endpoint on :9363
# =====================================================================================
if [[ -d /etc/clickhouse-server/config.d ]]; then
  echo "[ami-obs] Enabling ClickHouse Prometheus endpoint..."
  $SUDO tee /etc/clickhouse-server/config.d/40-prometheus.xml >/dev/null <<'EOF'
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
  $SUDO chmod 0644 /etc/clickhouse-server/config.d/40-prometheus.xml
  $SUDO systemctl restart clickhouse-server || true
fi

echo "[ami-obs] Observability stack baked into AMI."
