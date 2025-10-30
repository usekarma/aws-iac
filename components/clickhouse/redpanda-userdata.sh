  #!/usr/bin/env bash
  set -euxo pipefail
  exec >/var/log/user-data.redpanda.log 2>&1
  echo "[userdata:redpanda] start $(date -Is)"

  # ---------- SSM agent ----------
  dnf -y update || true
  dnf -y install amazon-ssm-agent xfsprogs jq curl || true
  systemctl enable --now amazon-ssm-agent || true

  # ---------- Mount data volume at /var/lib/redpanda ----------
  DEV_CAND="/dev/nvme1n1"
  if [ -b "$DEV_CAND" ]; then DEV="$DEV_CAND"; else DEV="/dev/xvdb"; fi
  mkdir -p /var/lib/redpanda

  if ! blkid "$DEV" >/dev/null 2>&1; then
    mkfs.xfs -f "$DEV"
  fi

  if ! grep -q " /var/lib/redpanda " /etc/fstab; then
    echo "$DEV /var/lib/redpanda xfs defaults,nofail 0 2" >> /etc/fstab
  fi
  mount -a
  mountpoint -q /var/lib/redpanda

  # ---------- Install Redpanda (repo + packages) ----------
  if [ ! -f /etc/yum.repos.d/redpanda.repo ]; then
    curl -1sLf 'https://packages.vectorized.io/rpk/redpanda.repo' | tee /etc/yum.repos.d/redpanda.repo
  fi
  dnf -y makecache || true
  dnf -y install redpanda redpanda-rpk || true

  # ---------- Start single broker (PLAINTEXT 9092, VPC-only) ----------
  PRIV_IP=$(hostname -I | awk '{print $1}')
  LOG_START="/var/log/redpanda-start.log"
  nohup rpk redpanda start --overprovisioned --smp 2 --memory 2G --reserve-memory 0M \
      --node-id 0 --check=false \
      --kafka-addr PLAINTEXT://0.0.0.0:${local.redpanda_port} \
      --advertise-kafka-addr PLAINTEXT://$${PRIV_IP}:${local.redpanda_port} \
      --rpc-addr 0.0.0.0:33145 --advertise-rpc-addr $${PRIV_IP}:33145 \
      --data-directory /var/lib/redpanda > "$LOG_START" 2>&1 &

  # Wait for broker port
  for i in {1..60}; do
    ss -lnt | grep -q ":${local.redpanda_port} " && break || sleep 1
  done

  # ---------- Create default ingest topic (RF=1 single-node) ----------
  sleep 3
  rpk topic create ch_ingest_normalized -p 3 -r 1 --brokers $${PRIV_IP}:${local.redpanda_port} || true

  # ---------- Record brokers for SSM / discovery ----------
  mkdir -p /var/local
  echo "$${PRIV_IP}:${local.redpanda_port}" > /var/local/redpanda_brokers.txt

  echo "[userdata:redpanda] done $(date -Is)"
