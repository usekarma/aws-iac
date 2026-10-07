#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -lt 2 || $# -gt 3 || ( $# -eq 3 && "$3" != "--destroy" ) ]]; then
  echo "Usage: ./scripts/plan.sh COMPONENT NICKNAME [--destroy]" >&2
  exit 1
fi
if [[ $# -eq 3 ]]; then
  exec ./scripts/deploy.sh --destroy-plan "$1" "$2"
fi
exec ./scripts/deploy.sh --plan "$1" "$2"
