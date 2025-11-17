#!/usr/bin/env bash
set -euxo pipefail

echo "[ami] Basic hardening..."
# Disable password auth if you always use SSH keys
sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd || systemctl restart ssh

# Time sync
dnf install -y chrony
systemctl enable --now chronyd

# CloudWatch / logs agent could be installed here if you want it baked in
