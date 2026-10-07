#!/usr/bin/env bash
set -euo pipefail

[[ "${AGENT_MODE:-0}" == "0" ]] || { echo "Agent mode blocks AMI/snapshot deletion" >&2; exit 1; }
[[ "${AWS_MUTATION_APPROVED:-}" == "1" && "${AWS_DESTRUCTIVE_APPROVED:-}" == "1" ]] || { echo "Explicit destructive approval of AMIs/snapshots required" >&2; exit 1; }
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
"$REPO_ROOT/scripts/preflight.sh"
export AWS_DEFAULT_REGION="$AWS_REGION" AWS_PAGER=""
KEEP=2
COMPONENT="${1:-clickhouse}"

echo "==> Finding AMIs tagged Component=$COMPONENT"

ami_text=$(aws ec2 describe-images \
  --owners self \
  --filters "Name=tag:Component,Values=$COMPONENT" \
  --query 'Images | sort_by(@, &CreationDate) | reverse() | [].ImageId' \
  --output text)
read -r -a amis <<< "$ami_text"

if [[ ${#amis[@]} -eq 0 ]]; then
  echo "No AMIs found for Component=$COMPONENT"
  exit 0
fi

echo "Found ${#amis[@]} AMIs total:"
printf '%s\n' "${amis[@]}"
echo

if (( ${#amis[@]} <= KEEP )); then
  echo "Nothing to prune (KEEP=$KEEP)"
  exit 0
fi

delete=("${amis[@]:$KEEP}")
echo "==> Will DELETE ${#delete[@]} AMIs:"
printf '%s\n' "${delete[@]}"
echo

read -r -p "Type DELETE-AMIS-AND-SNAPSHOTS to execute the approved list: " confirmation
[[ "$confirmation" == "DELETE-AMIS-AND-SNAPSHOTS" ]] || { echo "Deletion cancelled" >&2; exit 1; }
for ami in "${delete[@]}"; do
  snap=$(aws ec2 describe-images --image-ids "$ami" \
    --query 'Images[0].BlockDeviceMappings[0].Ebs.SnapshotId' \
    --output text)

  echo "→ Deregistering AMI: $ami"
  aws ec2 deregister-image --image-id "$ami"

  if [[ "$snap" != "None" && -n "$snap" ]]; then
    echo "→ Deleting snapshot: $snap"
    aws ec2 delete-snapshot --snapshot-id "$snap"
  else
    echo "⚠ No snapshot found for $ami (skipped)"
  fi
done

echo "Cleanup complete."
