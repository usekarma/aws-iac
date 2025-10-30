  #!/usr/bin/env bash
  set -euxo pipefail
  exec >/var/log/user-data.mongo.log 2>&1
  echo "[userdata:mongo] start $(date -Is)"

  # ---------- Base deps + SSM ----------
  dnf -y update || true
  dnf -y install amazon-ssm-agent xfsprogs jq curl || true
  systemctl enable --now amazon-ssm-agent || true

  # ---------- Identify & mount data volume at /var/lib/mongo ----------
  DEV_CAND="/dev/nvme1n1"
  if [ -b "$DEV_CAND" ]; then DEV="$DEV_CAND"; else DEV="/dev/xvdb"; fi
  mkdir -p /var/lib/mongo

  if ! blkid "$DEV" >/dev/null 2>&1; then
    mkfs.xfs -f "$DEV"
  fi

  if ! grep -q " /var/lib/mongo " /etc/fstab; then
    echo "$DEV /var/lib/mongo xfs defaults,nofail 0 2" >> /etc/fstab
  fi
  mount -a
  mountpoint -q /var/lib/mongo

  # ---------- MongoDB 7.0 repo (use RHEL 9 path on AL2023) ----------
  cat >/etc/yum.repos.d/mongodb-org-7.0.repo <<'REPO'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/9/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-7.0.asc
REPO

  dnf -y makecache || true
  dnf -y install mongodb-org || true

  # ---------- mongod config: bind to all (SG restricts), RS=rs0 ----------
  cat >/etc/mongod.conf <<CFG
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log
storage:
  dbPath: /var/lib/mongo
  journal:
    enabled: true
net:
  port: ${local.mongo_port}
  bindIp: 0.0.0.0
processManagement:
  timeZoneInfo: /usr/share/zoneinfo
replication:
  replSetName: rs0
CFG

  # Ensure ownership of data dir
  chown -R mongod:mongod /var/lib/mongo

  systemctl daemon-reload
  systemctl enable --now mongod

  # ---------- Wait for mongod socket ----------
  for i in {1..60}; do
    ss -ltn | grep -q ":${local.mongo_port} " && break || sleep 1
  done

  # ---------- Initiate single-node RS ----------
  PRIV_IP=$(hostname -I | awk '{print $1}')
  mongosh --quiet --eval 'rs.initiate({_id:"rs0", members:[{_id:0, host:"'"$PRIV_IP:${local.mongo_port}"'"}]})' || true

  # OPTIONAL auth bootstrap (disabled by default)
  # mongosh --quiet --eval 'use admin; db.createUser({user:"admin", pwd:"changeme", roles:[{role:"root", db:"admin"}]})'

  # ---------- Record RS URI for discovery ----------
  mkdir -p /var/local
  echo "mongodb://$${PRIV_IP}:${local.mongo_port}/?replicaSet=rs0" > /var/local/mongo_rs_uri.txt

  echo "[userdata:mongo] done $(date -Is)"
