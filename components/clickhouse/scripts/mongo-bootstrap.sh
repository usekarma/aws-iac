#!/usr/bin/env bash
set -euxo pipefail
exec > >(tee -a /var/log/mongo-bootstrap.log | logger -t mongo-bootstrap -s 2>/dev/console) 2>&1
echo "[mongo-bootstrap] start $(date -Is)"

# ---------------- Required env (from userdata) ----
: "${AWS_REGION:?missing AWS_REGION}"
: "${CLICKHOUSE_BUCKET:?missing CLICKHOUSE_BUCKET}"
: "${CLICKHOUSE_PREFIX:?missing CLICKHOUSE_PREFIX}"

: "${MONGO_MAJOR:?missing MONGO_MAJOR}"
: "${MONGO_PORT:?missing MONGO_PORT}"
: "${RS_NAME:?missing RS_NAME}"

: "${NODE_EXPORTER_VERSION:?missing NODE_EXPORTER_VERSION}"
: "${MONGODB_EXPORTER_VERSION:?missing MONGODB_EXPORTER_VERSION}"

# Optional:
# EBS_DEV, MNT, MARKER_FILE
# mongo-gen inputs: MONGO_GEN_REPO_URL, MONGO_GEN_BRANCH, MONGO_GEN_TOKEN_PARAM

# ---------------- Wait for basic network ----------------
for i in {1..60}; do
  curl -fsS https://aws.amazon.com >/dev/null && break || sleep 2
done

# ---------------- Detect package manager / distro -------
PM=""
DISTRO=""
if command -v dnf >/dev/null 2>&1; then
  PM="dnf" ; DISTRO="al2023"
elif command -v yum >/dev/null 2>&1; then
  PM="yum" ; DISTRO="al2"
elif command -v apt-get >/dev/null 2>&1; then
  PM="apt" ; DISTRO="ubuntu"
else
  echo "ERROR: No supported package manager found (dnf/yum/apt)" >&2
  exit 1
fi

# ---------------- Install & start SSM -------------------
if [[ "$PM" == "apt" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y || true
  apt-get install -y amazon-ssm-agent || true
else
  $PM -y update || true
  $PM -y install amazon-ssm-agent || true
fi
systemctl enable --now amazon-ssm-agent || true
systemctl is-active --quiet amazon-ssm-agent || true

# ---------------- Core tools (+ git/python for mongo-gen) ----------------
if [[ "$PM" == "apt" ]]; then
  apt-get install -y \
    ca-certificates gnupg jq rsync xfsprogs xz-utils curl awscli zstd netcat \
    git python3 python3-venv python3-pip || true
else
  $PM -y install \
    ca-certificates jq rsync xfsprogs dnf-plugins-core awscli zstd nmap-ncat \
    git python3 python3-pip --skip-broken || true
fi

# ---------------- Python 3.11 for mongo-gen (AL2023) ----------------
# AL2023 default python3 is 3.9; mongo-gen requires >=3.10.
if [[ "$DISTRO" == "al2023" ]]; then
  dnf -y install python3.11 python3.11-pip python3.11-devel || true
fi

# ---------------- Optional: pick & mount data disk -------
# IMPORTANT:
# - If MNT == /var/lib/mongo, mount it and DO NOT rsync+rm+symlink (that breaks).
# - If MNT != /var/lib/mongo, rsync then symlink /var/lib/mongo -> MNT.
if [[ -n "${MNT:-}" ]]; then
  mkdir -p "$MNT"

  pick_data_dev() {
    if [[ -n "${EBS_DEV:-}" && -b "${EBS_DEV}" ]]; then echo "${EBS_DEV}"; return 0; fi
    local rootpk
    rootpk="$(lsblk -no pkname "$(findmnt -no SOURCE /)" 2>/dev/null | head -n1)"
    lsblk -dn -o NAME,TYPE,SIZE \
    | awk '$2=="disk"{print $1" "$3}' \
    | sort -k2 -hr | awk '{print $1}' \
      | while read -r n; do
          [[ "$n" == "$rootpk" ]] && continue
          [[ -b "/dev/$n" ]] && { echo "/dev/$n"; break; }
        done
  }

  DATA_DEV=""
  for _ in {1..60}; do
    DATA_DEV="$(pick_data_dev || true)"
    [[ -n "$DATA_DEV" && -b "$DATA_DEV" ]] && break
    sleep 2
  done

  if [[ -n "$DATA_DEV" ]]; then
    if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
      mkfs.xfs -f "$DATA_DEV"
    fi

    UUID="$(blkid -s UUID -o value "$DATA_DEV")"
    # remove any older entries for MNT
    sed -i "\|[[:space:]]$MNT[[:space:]]|d;/^\/dev\/xvdb[[:space:]]/d" /etc/fstab
    grep -q "$UUID" /etc/fstab || echo "UUID=$UUID  $MNT  xfs  defaults,nofail  0  2" >> /etc/fstab

    mount -a || true

    if mountpoint -q "$MNT"; then
      echo "[mongo-bootstrap] Mounted $DATA_DEV at $MNT"

      mkdir -p /var/log/mongodb

      if [[ "$MNT" == "/var/lib/mongo" ]]; then
        :
      else
        mkdir -p /var/lib/mongo
        rsync -aHAX --delete /var/lib/mongo/ "$MNT"/ || true

        if mountpoint -q /var/lib/mongo; then
          echo "[mongo-bootstrap] WARN: /var/lib/mongo is a mountpoint; not removing" >&2
        else
          rm -rf /var/lib/mongo
          ln -s "$MNT" /var/lib/mongo
        fi
      fi
    else
      echo "WARN: $MNT is not a mountpoint after mount -a" >&2
    fi
  else
    echo "WARN: No data disk found; MongoDB will use default /var/lib/mongo" >&2
  fi
fi

# ---------------- Install MongoDB -----------------------
if [[ "$DISTRO" == "al2023" ]]; then
  cat >/etc/yum.repos.d/mongodb-org-${MONGO_MAJOR}.repo <<EOF
[mongodb-org-${MONGO_MAJOR}]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/9/mongodb-org/${MONGO_MAJOR}/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-${MONGO_MAJOR}.asc
EOF
  dnf clean all || true
  dnf install -y mongodb-org
elif [[ "$DISTRO" == "al2" ]]; then
  cat >/etc/yum.repos.d/mongodb-org-${MONGO_MAJOR}.repo <<EOF
[mongodb-org-${MONGO_MAJOR}]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/7/mongodb-org/${MONGO_MAJOR}/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-${MONGO_MAJOR}.asc
EOF
  yum clean all || true
  yum install -y mongodb-org
elif [[ "$DISTRO" == "ubuntu" ]]; then
  . /etc/os-release
  CODENAME="${VERSION_CODENAME:-$(lsb_release -sc 2>/dev/null || echo jammy)}"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL "https://pgp.mongodb.com/server-${MONGO_MAJOR}.asc" \
    | gpg --dearmor -o "/etc/apt/keyrings/mongodb-org-${MONGO_MAJOR}.gpg"
  echo "deb [arch=amd64,arm64 signed-by=/etc/apt/keyrings/mongodb-org-${MONGO_MAJOR}.gpg] https://repo.mongodb.org/apt/ubuntu ${CODENAME}/mongodb-org/${MONGO_MAJOR} multiverse" \
    >/etc/apt/sources.list.d/mongodb-org-${MONGO_MAJOR}.list
  apt-get update -y
  apt-get install -y mongodb-org netcat-openbsd
fi

# ---------------- Configure mongod ----------------------
mkdir -p /var/lib/mongo /var/log/mongodb

MONGO_USER="$(id -u mongod >/dev/null 2>&1 && echo mongod || echo mongodb)"
chown -R "$MONGO_USER":"$MONGO_USER" /var/lib/mongo /var/log/mongodb || true

cat >/etc/mongod.conf <<EOF
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log
storage:
  dbPath: /var/lib/mongo
net:
  port: ${MONGO_PORT}
  bindIp: 0.0.0.0
processManagement:
  timeZoneInfo: /usr/share/zoneinfo
replication:
  replSetName: ${RS_NAME}
EOF

systemctl enable --now mongod

for i in {1..60}; do
  nc -z 127.0.0.1 "${MONGO_PORT}" && break || sleep 1
done

if ! command -v mongosh >/dev/null 2>&1; then
  if [[ "$PM" == "apt" ]]; then
    apt-get install -y mongodb-mongosh
  else
    $PM -y install mongodb-mongosh || true
  fi
fi

# ---------- Robust single-node replica set init ----------
PRIV_IP="$(curl -fsS http://169.254.169.254/latest/meta-data/local-ipv4 || hostname -I | awk '{print $1}')"

mongosh --quiet "mongodb://127.0.0.1:${MONGO_PORT}/admin?directConnection=true" <<EOF_RS_INIT || true
(function() {
  const hello = db.hello();
  if (hello.isWritablePrimary === true) return;

  let needsInitiate = false;
  try { rs.status(); }
  catch (e) {
    if (e.code === 94 || /no replset config has been received/i.test(String(e))) needsInitiate = true;
  }

  if (needsInitiate) {
    rs.initiate({
      _id: "${RS_NAME}",
      members: [{ _id: 0, host: "${PRIV_IP}:${MONGO_PORT}" }]
    });
  }
})();
EOF_RS_INIT

mongosh --quiet "mongodb://127.0.0.1:${MONGO_PORT}/admin?directConnection=true" <<'EOF_RS_WAIT' || true
(function() {
  for (let i = 0; i < 60; i++) {
    try {
      const h = db.hello();
      if (h.isWritablePrimary === true) return;
    } catch (e) {}
    sleep(1000);
  }
})();
EOF_RS_WAIT

mongosh --quiet "mongodb://127.0.0.1:${MONGO_PORT}" --eval "db.adminCommand({ping:1})" || true
systemctl status mongod --no-pager || true

# ---------------- Mongo restore-or-init from S3 (latest dump-*, once) ----
RESTORE_MARKER="/var/local/mongo_manual_restore_done"

if [[ -f "$RESTORE_MARKER" ]]; then
  echo "[mongo-bootstrap] Mongo restore/init already performed; skipping."
else
  echo "[mongo-bootstrap] Looking for latest dump-* Mongo backup in S3..."
  LATEST_BACKUP="$(aws s3 ls "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/backups/" \
    | awk '$2 ~ /^dump-/ {print $2}' \
    | sort \
    | tail -n 1 || true)"

  if [[ -n "$LATEST_BACKUP" ]]; then
    echo "[mongo-bootstrap] Found Mongo backup in S3: $LATEST_BACKUP"
    mkdir -p /tmp/mongo-restore
    aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/backups/${LATEST_BACKUP}" /tmp/mongo-restore/ --recursive --region "${AWS_REGION}"
    mongorestore --gzip --drop --uri="mongodb://127.0.0.1:${MONGO_PORT}" /tmp/mongo-restore \
      && touch "$RESTORE_MARKER" \
      || echo "[mongo-bootstrap] WARNING: mongorestore failed"
    rm -rf /tmp/mongo-restore
  else
    echo "[mongo-bootstrap] No dump-* backup found; bootstrapping schema..."
    aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema_mongo/init-sales-schema.js"    /usr/local/bin/init-sales-schema.js    --region "${AWS_REGION}" || true
    aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema_mongo/init-reports-schema.js" /usr/local/bin/init-reports-schema.js --region "${AWS_REGION}" || true

    if [[ -s /usr/local/bin/init-sales-schema.js ]]; then
      mongosh --quiet "mongodb://127.0.0.1:${MONGO_PORT}" /usr/local/bin/init-sales-schema.js || true
      touch "$RESTORE_MARKER"
    fi
    if [[ -s /usr/local/bin/init-reports-schema.js ]]; then
      mongosh --quiet "mongodb://127.0.0.1:${MONGO_PORT}" /usr/local/bin/init-reports-schema.js || true
      touch "$RESTORE_MARKER"
    fi
  fi
fi

# ---------------- Download seed scripts (manual run) ---------------
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema_mongo/seed-sales-data.js"    /usr/local/bin/seed-sales-data.js    --region "${AWS_REGION}" || true
aws s3 cp "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/schema_mongo/seed-reports-data.js" /usr/local/bin/seed-reports-data.js --region "${AWS_REGION}" || true

# ---------------- Install mongo-gen from git (public or private) ----------------
MONGO_GEN_DIR="/opt/mongo-gen"
BRANCH="${MONGO_GEN_BRANCH:-main}"

if [[ -n "${MONGO_GEN_REPO_URL:-}" ]]; then
  echo "[mongo-bootstrap] Installing mongo-gen from git..."
  install -d -m 0755 /opt

  CLONE_URL="https://${MONGO_GEN_REPO_URL}"

  if [[ -n "${MONGO_GEN_TOKEN_PARAM:-}" ]]; then
    set +x
    GITHUB_TOKEN="$(aws ssm get-parameter \
      --name "${MONGO_GEN_TOKEN_PARAM}" \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region "${AWS_REGION}")"
    set -x

    CLONE_URL="https://${GITHUB_TOKEN}@${MONGO_GEN_REPO_URL}"
    unset GITHUB_TOKEN
  fi

  rm -rf "${MONGO_GEN_DIR}"
  git clone --branch "${BRANCH}" "${CLONE_URL}" "${MONGO_GEN_DIR}"

  # ---- use python3.11 on AL2023; fallback otherwise ----
  if [[ "$DISTRO" == "al2023" ]] && command -v python3.11 >/dev/null 2>&1; then
    PYBIN="$(command -v python3.11)"
  else
    PYBIN="$(command -v python3)"
  fi

  "$PYBIN" -m venv "${MONGO_GEN_DIR}/.venv"
  # shellcheck disable=SC1091
  source "${MONGO_GEN_DIR}/.venv/bin/activate"
  python --version
  pip install -U pip
  pip install -e "${MONGO_GEN_DIR}"
  deactivate || true

  cat >/usr/local/bin/mongo-gen <<'RUNMG'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/mongo-gen
source .venv/bin/activate
exec mongo-gen "$@"
RUNMG
  chmod +x /usr/local/bin/mongo-gen

  echo "[mongo-bootstrap] mongo-gen installed at ${MONGO_GEN_DIR}"
else
  echo "[mongo-bootstrap] Skipping mongo-gen install (MONGO_GEN_REPO_URL not set)"
fi

# ---------------- Exporters (Mongo & Node) ---------------
ARCH="amd64"
case "$(uname -m)" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
esac

install -d -m 0755 /usr/local/src/exporters
pushd /usr/local/src/exporters >/dev/null

NODE_TGZ="node_exporter-${NODE_EXPORTER_VERSION}.linux-${ARCH}.tar.gz"
curl -fL -o "$NODE_TGZ" "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${NODE_TGZ}"
tar -xzf "$NODE_TGZ"
install -m 0755 "node_exporter-${NODE_EXPORTER_VERSION}.linux-${ARCH}/node_exporter" /usr/local/bin/node_exporter

cat >/etc/systemd/system/node_exporter.service <<EOF
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=root
ExecStart=/usr/local/bin/node_exporter --web.listen-address=":9100"
Restart=always

[Install]
WantedBy=multi-user.target
EOF

MONGOEXP_TGZ="mongodb_exporter-${MONGODB_EXPORTER_VERSION}.linux-${ARCH}.tar.gz"
curl -fL -o "$MONGOEXP_TGZ" "https://github.com/percona/mongodb_exporter/releases/download/v${MONGODB_EXPORTER_VERSION}/${MONGOEXP_TGZ}"
tar -xzf "$MONGOEXP_TGZ"
install -m 0755 "mongodb_exporter-${MONGODB_EXPORTER_VERSION}.linux-${ARCH}/mongodb_exporter" /usr/local/bin/mongodb_exporter

popd >/dev/null

cat >/etc/systemd/system/mongodb_exporter.service <<EOF
[Unit]
Description=MongoDB Exporter
After=network-online.target mongod.service
Wants=network-online.target

[Service]
User=root
ExecStart=/usr/local/bin/mongodb_exporter \
  --mongodb.uri="mongodb://127.0.0.1:${MONGO_PORT}/admin?directConnection=true" \
  --web.listen-address=":9216"
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter mongodb_exporter

curl -fsS http://127.0.0.1:9100/metrics | head -n 5 || true
curl -fsS http://127.0.0.1:9216/metrics | head -n 5 || true

# ---------------- Manual S3 backup script (no timer) ----
install -m 0755 -d /usr/local/bin
cat >/usr/local/bin/mongo-backup-s3.sh <<BKS
#!/usr/bin/env bash
set -euo pipefail

TS="\$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/tmp/mongo-dump-\$TS"

echo "[mongo-backup] Dumping MongoDB from localhost:${MONGO_PORT}..."
mongodump --uri="mongodb://127.0.0.1:${MONGO_PORT}" --gzip --out "\$OUT"

echo "[mongo-backup] Uploading backup to s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/backups/dump-\$TS/ (region=${AWS_REGION})..."
aws s3 cp "\$OUT" "s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/backups/dump-\$TS/" --recursive --region "${AWS_REGION}"

rm -rf "\$OUT"
echo "[mongo-backup] Backup complete: s3://${CLICKHOUSE_BUCKET}/${CLICKHOUSE_PREFIX}/backups/dump-\$TS/"
BKS
chmod +x /usr/local/bin/mongo-backup-s3.sh

# ---------------- Marker -------------------------------
if [[ -n "${MARKER_FILE:-}" ]]; then
  echo "$(date -u +%FT%TZ) BOOTSTRAP_OK" > "${MARKER_FILE}"
fi

echo "[mongo-bootstrap] done $(date -Is)"
