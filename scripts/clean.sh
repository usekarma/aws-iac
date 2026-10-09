#!/bin/bash
set -euo pipefail

[[ "${AGENT_MODE:-0}" == "0" && "${LOCAL_STATE_CLEANUP_APPROVED:-}" == "1" ]] || { echo "Local state cleanup requires reviewed operator approval and is blocked in agent mode" >&2; exit 1; }

echo "🧹 Cleaning local Terraform and Terragrunt artifacts..."

# Remove temp working directories used by deploy.sh
if [[ -d .terragrunt-work ]]; then
  rm -rf .terragrunt-work
  echo "🗑️  Removed .terragrunt-work/"
fi

# Clean up any Terraform files accidentally placed in project root
rm -rf .terraform
rm -f .terraform.lock.hcl
rm -f terraform.tfstate*
rm -f crash.log

echo "✅ Clean complete."
