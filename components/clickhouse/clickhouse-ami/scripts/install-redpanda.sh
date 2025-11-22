#!/usr/bin/env bash
# install-redpanda.sh — Build-time Redpanda install for AL2023 (EL9)

set -euxo pipefail

echo "[redpanda-install] Starting Redpanda AMI provisioning..."

# ----------------------------
# Base OS tooling + SSM agent
# ----------------------------
echo "[redpanda-install] Installing base tools and SSM agent..."
dnf update -y
dnf install -y \
  shadow-utils \
  jq \
  amazon-ssm-agent

systemctl enable --now amazon-ssm-agent || true

# ------------------------------------------------------
# Configure Redpanda yum repo (official AL2023/EL9 path)
# ------------------------------------------------------
echo "[redpanda-install] Configuring Redpanda repository for EL9/AL2023..."

# NOTE: Packer runs this as root, so no sudo.
curl -1sLf \
  'https://dl.redpanda.com/nzc4ZYQK3WRGd9sy/redpanda/cfg/setup/bash.rpm.sh' \
  | bash

# -------------------------------
# Install Redpanda + CLI + tuner
# -------------------------------
echo "[redpanda-install] Installing redpanda, rpk and tuner..."
dnf install -y \
  redpanda \
  redpanda-rpk \
  redpanda-tuner

# ----------------------------------------
# Make sure Redpanda is *not* auto-running
# ----------------------------------------
echo "[redpanda-install] Disabling redpanda service for AMI..."
systemctl stop redpanda || true
systemctl disable redpanda || true

# -----------------
# Final clean-up
# -----------------
echo "[redpanda-install] Cleaning up dnf caches..."
dnf clean all
rm -rf /var/cache/dnf || true

echo "[redpanda-install] Redpanda AMI provisioning complete."
