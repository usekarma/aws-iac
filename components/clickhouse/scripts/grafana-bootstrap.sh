#!/usr/bin/env bash
# grafana-bootstrap.sh — auto-install ClickHouse & MongoDB plugins if missing

set -euo pipefail

# =========================
# Hard-coded configuration
# =========================
GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS="${GRAFANA_PASS:-admin}"

PROM_URL="${PROM_URL:-http://127.0.0.1:9090}"
PROM_DS_NAME="${PROM_DS_NAME:-Prometheus}"

# ClickHouse config
CLICKHOUSE_URL="${CLICKHOUSE_URL:-http://127.0.0.1:8123}"          # HTTP endpoint (for Altinity plugin)
CLICKHOUSE_DS_NAME="${CLICKHOUSE_DS_NAME:-ClickHouse}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-sales}"
# Altinity plugin id:
CLICKHOUSE_PLUGIN_TYPE="${CLICKHOUSE_PLUGIN_TYPE:-vertamedia-clickhouse-datasource}"
CLICKHOUSE_SERVER_ADDR="${CLICKHOUSE_SERVER_ADDR:-127.0.0.1}"
CLICKHOUSE_SERVER_PORT="${CLICKHOUSE_SERVER_PORT:-8123}"           # HTTP port for Altinity

CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-127.0.0.1}"
CLICKHOUSE_TCP_PORT="${CLICKHOUSE_TCP_PORT:-9000}"   # native protocol (still useful for docs)
CLICKHOUSE_PROTOCOL="${CLICKHOUSE_PROTOCOL:-native}" # or "http"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-}"

# Mongo config
MONGO_DS_NAME="${MONGO_DS_NAME:-MongoDB}"
MONGO_DB="${MONGO_DB:-sales}"
MONGO_URL="${MONGO_URL:-mongodb://127.0.0.1:27017/sales}"          # full connection string incl. DB
MONGO_PLUGIN_TYPE="${MONGO_PLUGIN_TYPE:-grafana-mongodb-datasource}"

MONGO_CONN_STRING="${MONGO_CONN_STRING:-mongodb://127.0.0.1:27017/${MONGO_DB}}"
MONGO_USER="${MONGO_USER:-}"
MONGO_PASSWORD="${MONGO_PASSWORD:-}"

: "${CLICKHOUSE_BUCKET:?CLICKHOUSE_BUCKET is required}"
: "${CLICKHOUSE_PREFIX:?CLICKHOUSE_PREFIX is required}"

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

  # MongoDB (metrics via Prometheus)
  12079  # MongoDB (Percona exporter)
  2583   # MongoDB Generic
  20867  # MongoDB (Percona/K8s style)
  7353   # MongoDB Overview (Percona PMM)
  16490  # MongoDB Cluster/Replication (Opstree)
  14997  # MongoDB General variant

  # ClickHouse (Prom-based, existing)
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
# Install plugins if missing
# ===========
install_plugin() {
  local plugin="$1"
  if ! sudo grafana-cli plugins ls 2>/dev/null | grep -q "$plugin"; then
    echo "[grafana] installing plugin: $plugin"
    sudo grafana-cli plugins install "$plugin" || {
      echo "[grafana] failed to install $plugin" >&2
      return 1
    }
    RESTART_REQUIRED=1
  else
    echo "[grafana] plugin already installed: $plugin"
  fi
}

if command -v grafana-cli >/dev/null 2>&1; then
  RESTART_REQUIRED=0
  install_plugin "$CLICKHOUSE_PLUGIN_TYPE"
  install_plugin "$MONGO_PLUGIN_TYPE"

  if [[ "$RESTART_REQUIRED" -eq 1 ]]; then
    echo "[grafana] restarting grafana-server..."
    sudo systemctl restart grafana-server || true
    sleep 5
  fi
else
  echo "[grafana] WARNING: grafana-cli not found; skipping plugin installation"
fi

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

DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "${GRAFANA_URL}/api/datasources/name/${PROM_DS_NAME}" || true)"

if [[ -n "$DS_JSON" ]] && echo "$DS_JSON" | jq -e .id >/dev/null 2>&1; then
  DS_ID="$(echo "$DS_JSON" | jq -r .id)"
else
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
echo "[grafana] Prometheus datasource id=${DS_ID} uid=${DS_UID}"

# ===========
# Create ClickHouse and Mongo datasources (initial create)
# ===========
create_clickhouse() {
  echo "[grafana] creating ClickHouse datasource (Altinity) with uid=clickhouse-main"

  local payload
  payload="$(mktemp)"

  jq -n \
    --arg name     "$CLICKHOUSE_DS_NAME" \
    --arg url      "$CLICKHOUSE_URL" \
    --arg db       "$CLICKHOUSE_DB" \
    --arg user     "$CLICKHOUSE_USER" \
    --arg pass     "$CLICKHOUSE_PASSWORD" \
    --arg ptype    "$CLICKHOUSE_PLUGIN_TYPE" \
  '{
    name: $name,
    uid: "clickhouse-main",
    type: $ptype,
    access: "proxy",
    url: $url,
    isDefault: false,
    jsonData: {
      defaultDatabase: $db,
      username: $user,
      tlsSkipVerify: true
    },
    secureJsonData: {
      password: $pass
    }
  }' > "$payload"

  curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    -X POST \
    --data-binary @"$payload" \
    "${GRAFANA_URL}/api/datasources" >/dev/null || true

  rm -f "$payload"
}

create_mongo() {
  echo "[grafana] creating MongoDB datasource"

  local payload
  payload="$(mktemp)"

  jq -n \
    --arg name  "$MONGO_DS_NAME" \
    --arg uri   "$MONGO_CONN_STRING" \
    --arg db    "$MONGO_DB" \
    --arg user  "$MONGO_USER" \
    --arg pass  "$MONGO_PASSWORD" \
    --arg ptype "$MONGO_PLUGIN_TYPE" \
  '{
    name: $name,
    type: $ptype,
    access: "proxy",
    url: "",
    jsonData: {
      defaultDatabase: $db,
      username: $user
    },
    secureJsonData: {
      uri: $uri,
      password: $pass
    }
  }' > "$payload"

  curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    -X POST \
    --data-binary @"$payload" \
    "${GRAFANA_URL}/api/datasources" >/dev/null || true

  rm -f "$payload"
}

create_clickhouse
create_mongo

echo "[grafana] plugins and datasources (initial) created."

# ===========
# Check for ClickHouse plugin
# ===========
SKIP_CH=0
echo "[grafana] checking for ClickHouse plugin '${CLICKHOUSE_PLUGIN_TYPE}'"

PLUGINS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "${GRAFANA_URL}/api/plugins" || true)"

if [[ -z "$PLUGINS_JSON" ]] || ! echo "$PLUGINS_JSON" | jq -e --arg t "$CLICKHOUSE_PLUGIN_TYPE" \
     'map(select(.id == $t and .enabled == true)) | length > 0' >/dev/null 2>&1; then
  echo "[grafana] WARNING: ClickHouse plugin '${CLICKHOUSE_PLUGIN_TYPE}' not found or not enabled; skipping ClickHouse dashboard."
  SKIP_CH=1
else
  echo "[grafana] ClickHouse plugin '${CLICKHOUSE_PLUGIN_TYPE}' is present and enabled."
fi

# ===========
# Check for MongoDB plugin
# ===========
SKIP_MONGO=0
echo "[grafana] checking for MongoDB plugin '${MONGO_PLUGIN_TYPE}'"

if [[ -z "$PLUGINS_JSON" ]]; then
  PLUGINS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/plugins" || true)"
fi

if [[ -z "$PLUGINS_JSON" ]] || ! echo "$PLUGINS_JSON" | jq -e --arg t "$MONGO_PLUGIN_TYPE" \
     'map(select(.id == $t and .enabled == true)) | length > 0' >/dev/null 2>&1; then
  echo "[grafana] WARNING: MongoDB plugin '${MONGO_PLUGIN_TYPE}' not found or not enabled; skipping MongoDB dashboard."
  SKIP_MONGO=1
else
  echo "[grafana] MongoDB plugin '${MONGO_PLUGIN_TYPE}' is present and enabled."
fi

# ===========
# Ensure ClickHouse datasource (if plugin exists)
# ===========
if [[ "$SKIP_CH" -eq 0 ]]; then
  echo "[grafana] ensuring ClickHouse datasource '${CLICKHOUSE_DS_NAME}'"

  CH_DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/datasources/name/${CLICKHOUSE_DS_NAME}" || true)"

  if [[ -n "$CH_DS_JSON" ]] && echo "$CH_DS_JSON" | jq -e .id >/dev/null 2>&1; then
    CH_DS_ID="$(echo "$CH_DS_JSON" | jq -r .id)"
  else
    ch_ds_payload="$(mktemp)"
    jq -n \
      --arg name   "$CLICKHOUSE_DS_NAME" \
      --arg url    "$CLICKHOUSE_URL" \
      --arg db     "$CLICKHOUSE_DB" \
      --arg ptype  "$CLICKHOUSE_PLUGIN_TYPE" \
    '{
      name: $name,
      uid: "clickhouse-main",
      type: $ptype,
      access: "proxy",
      url: $url,
      isDefault: false,
      jsonData: {
        defaultDatabase: $db,
        tlsSkipVerify: true
      }
    }' > "$ch_ds_payload"

    CH_DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
      -H "Content-Type: application/json" -X POST \
      --data-binary @"$ch_ds_payload" \
      "${GRAFANA_URL}/api/datasources")"
    rm -f "$ch_ds_payload"
    CH_DS_ID="$(echo "$CH_DS_JSON" | jq -r .id)"
  fi

  CH_DS_UID="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/datasources/${CH_DS_ID}" | jq -r .uid)"
  echo "[grafana] ClickHouse datasource id=${CH_DS_ID} uid=${CH_DS_UID}"
fi

# ===========
# Ensure MongoDB datasource (if plugin exists)
# ===========
if [[ "$SKIP_MONGO" -eq 0 ]]; then
  echo "[grafana] ensuring MongoDB datasource '${MONGO_DS_NAME}'"

  MONGO_DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/datasources/name/${MONGO_DS_NAME}" || true)"

  if [[ -n "$MONGO_DS_JSON" ]] && echo "$MONGO_DS_JSON" | jq -e .id >/dev/null 2>&1; then
    MONGO_DS_ID="$(echo "$MONGO_DS_JSON" | jq -r .id)"
  else
    mongo_ds_payload="$(mktemp)"
    jq -n \
      --arg name  "$MONGO_DS_NAME" \
      --arg uri   "$MONGO_CONN_STRING" \
      --arg db    "$MONGO_DB" \
      --arg user  "$MONGO_USER" \
      --arg pass  "$MONGO_PASSWORD" \
      --arg ptype "$MONGO_PLUGIN_TYPE" \
    '{
      name: $name,
      type: $ptype,
      access: "proxy",
      url: "",
      isDefault: false,
      jsonData: {
        defaultDatabase: $db,
        username: $user
      },
      secureJsonData: {
        uri: $uri,
        password: $pass
      }
    }' > "$mongo_ds_payload"

    MONGO_DS_JSON="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
      -H "Content-Type: application/json" -X POST \
      --data-binary @"$mongo_ds_payload" \
      "${GRAFANA_URL}/api/datasources")"
    rm -f "$mongo_ds_payload"
    MONGO_DS_ID="$(echo "$MONGO_DS_JSON" | jq -r .id)"
  fi

  MONGO_DS_UID="$(curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/datasources/${MONGO_DS_ID}" | jq -r .uid)"
  echo "[grafana] MongoDB datasource id=${MONGO_DS_ID} uid=${MONGO_DS_UID}"
fi

# ===========
# Import helper (portable: uses files + --slurpfile)
# ===========
import_dash () {
  local ID="$1"
  echo "[dashboard] importing id=${ID}"

  local rev
  rev="$(curl -fsS "https://grafana.com/api/dashboards/${ID}/revisions" \
          | jq -r '.items | max_by(.revision) | .revision')"
  [[ -n "$rev" && "$rev" != "null" ]] || { echo "  ! no revisions for ${ID}"; return 1; }

  local dash tmp_wrap resp
  dash="$(mktemp)"
  curl -fsS "https://grafana.com/api/dashboards/${ID}/revisions/${rev}/download" > "$dash"

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

  tmp_wrap="$(mktemp)"
  jq -n --slurpfile d "$dash" --argjson inputs "$inputs" '{
    dashboard: $d[0],
    overwrite: true,
    inputs: $inputs,
    folderId: 0
  }' > "$tmp_wrap"

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
# Import all Prom-based dashboards
# ===========
for id in "${DASH_IDS[@]}"; do
  import_dash "$id" || echo "  ! failed id=${id}"
done

# ===========
# Import custom ClickHouse dashboards from S3 (if plugin exists)
# ===========
if [[ "$SKIP_CH" -eq 0 ]]; then
  echo "[grafana] importing custom ClickHouse dashboards from s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/dashboards"

  if [[ -z "$CLICKHOUSE_BUCKET" ]]; then
    echo "[grafana] WARNING: CLICKHOUSE_BUCKET not set; skipping custom ClickHouse dashboard import."
  else
    # List all .json objects under the prefix
    mapfile -t DASH_KEYS < <(aws s3 ls "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/dashboards/" \
      | awk '/\.json$/ {print $4}')

    if [[ "${#DASH_KEYS[@]}" -eq 0 ]]; then
      echo "[grafana] no .json dashboards found under s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/dashboards/"
    else
      for key in "${DASH_KEYS[@]}"; do
        echo "[grafana] importing dashboard from s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/dashboards/${key}"

        TMP_DASH="$(mktemp)"
        WRAP_DASH="$(mktemp)"
        RESP_DASH="$(mktemp)"

        if aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/dashboards/${key}" "$TMP_DASH"; then
          if [[ ! -s "$TMP_DASH" ]]; then
            echo "[grafana] WARNING: downloaded dashboard file is empty; skipping import: ${key}"
          else
            jq -n --slurpfile d "$TMP_DASH" '{
              dashboard: $d[0],
              overwrite: true,
              folderId: 0
            }' > "$WRAP_DASH"

            CODE="$(curl -sS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
              -H "Content-Type: application/json" \
              -X POST "${GRAFANA_URL}/api/dashboards/import" \
              --data-binary @"$WRAP_DASH" \
              -w '%{http_code}' -o "$RESP_DASH" || true)"

            if [[ "$CODE" -ge 200 && "$CODE" -lt 300 ]]; then
              echo "  ✓ imported ${key}"
            else
              echo "  ! import failed for ${key} http=${CODE}"
              sed -n '1,200p' "$RESP_DASH" >&2
            fi
          fi
        else
          echo "[grafana] WARNING: failed to download dashboard JSON from S3: ${key}"
        fi

        rm -f "$TMP_DASH" "$WRAP_DASH" "$RESP_DASH"
      done
    fi
  fi
else
  echo "[grafana] Skipping ClickHouse dashboards (no plugin)."
fi

echo "[grafana] dashboard import complete."
