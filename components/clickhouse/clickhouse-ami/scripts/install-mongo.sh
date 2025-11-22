#!/usr/bin/env bash
# scripts/install-mongo.sh
# AMI-safe MongoDB install for Amazon Linux 2023

set -euo pipefail

echo "[mongo-install] Starting MongoDB AMI provisioning..."

# Terragrunt/Packer will usually pass MONGO_MAJOR=7
MONGO_MAJOR="${MONGO_MAJOR:-7}"

# Normalize to a series string that matches Mongo's repo layout
# e.g. 7 -> 7.0
if [[ "${MONGO_MAJOR}" == "7" ]]; then
  MONGO_SERIES="7.0"
else
  MONGO_SERIES="${MONGO_MAJOR}"
fi

echo "[mongo-install] Using MongoDB series: ${MONGO_SERIES}"

# Basic OS update (no-op if current)
dnf update -y || true

# Tools we may want (lsb-release is NOT available on AL2023)
dnf install -y \
  shadow-utils \
  jq || true

# -------------------------------------------------------------------
# MongoDB YUM repo for RHEL 9 / x86_64
# NOTE: both baseurl and gpgkey must use the series (e.g. 7.0)
# -------------------------------------------------------------------
cat >/etc/yum.repos.d/mongodb-org-${MONGO_SERIES}.repo <<EOF
[mongodb-org-${MONGO_SERIES}]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/9/mongodb-org/${MONGO_SERIES}/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-${MONGO_SERIES}.asc
EOF

echo "[mongo-install] Repo file written to /etc/yum.repos.d/mongodb-org-${MONGO_SERIES}.repo"
echo "[mongo-install] Installing mongodb-org..."

# The curl-minimal vs curl mess is internal to AL2023's repo;
# let dnf resolve it with --allowerasing
dnf install -y --allowerasing mongodb-org

echo "[mongo-install] Enabling mongod systemd service (but not starting)..."
systemctl enable mongod || true

# -------------------------------------------------------------------
# Install amazon-ssm-agent so the AMI is SSM-ready
# -------------------------------------------------------------------
if ! command -v amazon-ssm-agent >/dev/null 2>&1; then
  echo "[mongo-install] Installing amazon-ssm-agent..."
  dnf install -y amazon-ssm-agent
  systemctl enable amazon-ssm-agent || true
fi

# -------------------------------------------------------------------
# Clean up for AMI
# -------------------------------------------------------------------
echo "[mongo-install] Cleaning up..."
rm -rf /var/log/*
dnf clean all || true

echo "[mongo-install] MongoDB AMI provisioning complete."
