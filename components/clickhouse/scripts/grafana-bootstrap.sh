#!/usr/bin/env bash
# grafana-bootstrap.sh — Hardcoded vars + portable jq usage + file-based POSTs

set -euo pipefail

# =========================
# Hard-coded configuration
# =========================
GRAFANA_URL="https://grafana.usekarma.dev"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"
PROM_URL="http://127.0.0.1:9090"
PROM_DS_NAME="Prometheus"

# Default dashboard IDs (override by editing this array)
DASH_IDS=(
  # Core / Prometheus
  1860   # Node Exporter Full
  3662   # Prometheus 2.0 Stats
  14205  # Prometheus Overview
  14508  # Prometheus Alerts & Rules Summary
  12866  # Prometheus Performance & Scrape Health

  # Redpanda / Kafka
  18134  # Redpanda Default Overview
  18135  # Redpanda Ops / SRE View
  18132  # Kafka Topic Metrics (Redpanda)
  18133  # Kafka Java Consumer Metrics
  18136  # Kafka Consumer Offsets
  22164  # Kafka Producer Metrics
  22157  # Redpanda Connect Monitoring

  # MongoDB
  12079  # MongoDB (Percona exporter)
  2583   # MongoDB Generic
  20867  # MongoDB (Percona/K8s style)
  7353   # MongoDB Overview (Percona PMM)
  16490  # MongoDB Cluster/Replication (Opstree)
  14997  # MongoDB General variant

  # ClickHouse
  14192  # ClickHouse Internal Prom exporter
  13334  # ClickHouse State
  14719  # ClickHouse ANAL
  13500  # ClickHouse Internal Exporter alt
  882    # ClickHouse (f1yegor exporter legacy)
)

# ===========
# Prereqs
# ===========
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need curl
need jq

# ===========
# Wait for Grafana up
# ===========
echo "[grafana] waiting for ${GRAFANA_URL} to be healthy..."
for i in {1..90}; do
  if curl -fsS "${GRAFANA_URL}/api/health" >/dev/null 2>&1; then
    echo "[grafana] up."
    break
  fi
  sleep 2
  [[ $i -eq 90 ]] && echo "[grafana] never became ready; proceeding anyway"
done

# ===========
# Ensure Prometheus datasource
# ===========
echo "[grafana] ensuring datasource '${PROM_DS_NAME}' -> ${PROM_URL}"

# Try GET existing
DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "${GRAFANA_URL}/api/datasources/name/${PROM_DS_NAME}" || true)"

if [[ -n "$DS_JSON" ]] && echo "$DS_JSON" | jq -e .id >/dev/null 2>&1; then
  DS_ID="$(echo "$DS_JSON" | jq -r .id)"
else
  # Create
  ds_payload="$(mktemp)"
  jq -n --arg name "$PROM_DS_NAME" --arg url "$PROM_URL" '{
      name: $name, type: "prometheus", access: "proxy", url: $url, isDefault: true,
      jsonData: { httpMethod: "POST" }
    }' > "$ds_payload"

  DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" -X POST \
    --data-binary @"$ds_payload" \
    "${GRAFANA_URL}/api/datasources")"
  rm -f "$ds_payload"
  DS_ID="$(echo "$DS_JSON" | jq -r .id)"
fi

DS_UID="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "${GRAFANA_URL}/api/datasources/${DS_ID}" | jq -r .uid)"
echo "[grafana] datasource id=${DS_ID} uid=${DS_UID}"

# ===========
# Import helper (portable: uses files + --slurpfile)
# ===========
import_dash () {
  local ID="$1"
  echo "[dashboard] importing id=${ID}"

  # 1) Latest revision
  local rev
  rev="$(curl -fsS "https://grafana.com/api/dashboards/${ID}/revisions" \
          | jq -r '.items | max_by(.revision) | .revision')"
  [[ -n "$rev" && "$rev" != "null" ]] || { echo "  ! no revisions for ${ID}"; return 1; }

  # 2) Download JSON to file
  local dash tmp_wrap resp
  dash="$(mktemp)"
  curl -fsS "https://grafana.com/api/dashboards/${ID}/revisions/${rev}/download" > "$dash"

  # 3) Build inputs from __inputs; fallback to common names if absent
  local inputs
  inputs="$(jq --arg dsUid "$DS_UID" '
      (.__inputs // [])
      | map(select((.pluginId=="prometheus") or (.type=="datasource")))
      | unique_by(.name)
      | map({name:.name, type:"datasource", pluginId:"prometheus", value:$dsUid})
    ' "$dash")"
  if [[ "$(echo "$inputs" | jq 'length')" -eq 0 ]]; then
    inputs="$(jq -n --arg dsUid "$DS_UID" '[
      {name:"DS_PROMETHEUS", type:"datasource", pluginId:"prometheus", value:$dsUid},
      {name:"PROMETHEUS",    type:"datasource", pluginId:"prometheus", value:$dsUid}
    ]')"
  fi

  # 4) Wrap for import using --slurpfile to load dashboard JSON
  tmp_wrap="$(mktemp)"
  jq -n --slurpfile d "$dash" --argjson inputs "$inputs" '{
    dashboard: $d[0],
    overwrite: true,
    inputs: $inputs,
    folderId: 0
  }' > "$tmp_wrap"

  # 5) POST and capture HTTP code (avoid --fail-with-body)
  resp="$(mktemp)"
  code="$(curl -sS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
         -H "Content-Type: application/json" \
         -X POST "${GRAFANA_URL}/api/dashboards/import" \
         --data-binary @"$tmp_wrap" \
         -w '%{http_code}' -o "$resp" || true)"

  if [[ "$code" -ge 200 && "$code" -lt 300 ]]; then
    echo "  ✓ imported id=${ID} rev=${rev}"
  else
    echo "  ! import failed id=${ID} rev=${rev} http=${code}"
    sed -n '1,200p' "$resp" >&2
  fi

  rm -f "$dash" "$tmp_wrap" "$resp"
}

# ===========
# Import all dashboards
# ===========
for id in "${DASH_IDS[@]}"; do
  import_dash "$id" || echo "  ! failed id=${id}"
done

echo "[grafana] dashboard import complete."
