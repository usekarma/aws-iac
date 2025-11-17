#!/usr/bin/env bash
set -euo pipefail

# Optional: version passed from Packer via env var
CLICKHOUSE_VERSION="${CLICKHOUSE_VERSION:-}"

echo "[ami] CLICKHOUSE_VERSION='${CLICKHOUSE_VERSION}' (empty means latest)"

echo "[ami] Updating OS..."
sudo dnf -y update

echo "[ami] Installing repo tooling (yum-utils / dnf-plugins-core)..."
sudo dnf install -y yum-utils

echo "[ami] Adding ClickHouse RPM repo..."
if command -v yum-config-manager >/dev/null 2>&1; then
  sudo yum-config-manager --add-repo https://packages.clickhouse.com/rpm/clickhouse.repo
else
  echo "[ami] ERROR: yum-config-manager not found; cannot add ClickHouse repo" >&2
  exit 1
fi

echo "[ami] Installing ClickHouse server + client..."
if [[ -n "${CLICKHOUSE_VERSION}" ]]; then
  echo "[ami] Installing *pinned* ClickHouse version: ${CLICKHOUSE_VERSION}"
  # NOTE: here CLICKHOUSE_VERSION must match RPM version string, e.g. 25.10.2.65-1
  sudo dnf install -y \
    "clickhouse-common-static-${CLICKHOUSE_VERSION}" \
    "clickhouse-server-${CLICKHOUSE_VERSION}" \
    "clickhouse-client-${CLICKHOUSE_VERSION}"
else
  echo "[ami] Installing latest ClickHouse from repo (no version pinned)..."
  sudo dnf install -y clickhouse-server clickhouse-client
fi

echo "[ami] Setting up directories..."
sudo install -d -o clickhouse -g clickhouse -m 0750 /var/lib/clickhouse
sudo install -d -o clickhouse -g clickhouse -m 0750 /var/log/clickhouse-server

echo "[ami] Writing minimal config (listen on 0.0.0.0)..."
cat <<'EOF' | sudo tee /etc/clickhouse-server/config.d/listen.xml >/dev/null
<clickhouse>
  <listen_host>0.0.0.0</listen_host>
</clickhouse>
EOF

echo "[ami] Enabling ClickHouse service (best-effort)..."
if ! sudo systemctl enable clickhouse-server; then
  echo "[ami] WARNING: systemctl enable clickhouse-server failed (likely missing systemd-sysv-install); continuing anyway."
fi

echo "[ami] Smoke test: start, SELECT 1, stop..."
sudo systemctl start clickhouse-server
sleep 5
clickhouse-client -q 'SELECT 1'
sudo systemctl stop clickhouse-server

echo "[ami] Cleanup..."
sudo rm -rf /var/log/clickhouse-server/*
sudo dnf clean all
sudo rm -rf /var/cache/dnf

echo "[ami] AMI provisioning complete."
