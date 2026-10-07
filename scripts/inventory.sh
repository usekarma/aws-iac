#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
OUTPUT=""
if [[ $# -gt 0 ]]; then
  [[ $# -eq 2 && "$1" == "--output" ]] || { echo "Usage: inventory.sh [--output NEW_PRIVATE_DIR]" >&2; exit 1; }
  OUTPUT="$2"
  [[ ! -e "$OUTPUT" ]] || { echo "Inventory output must be a new directory" >&2; exit 1; }
fi
./scripts/preflight.sh
if [[ -n "$OUTPUT" ]]; then umask 077; mkdir -p "$OUTPUT"; fi
emit() {
  local name="$1"
  shift
  if [[ -n "$OUTPUT" ]]; then
    "${AWS[@]}" "$@" > "$OUTPUT/$name.json"
  else
    "${AWS[@]}" "$@"
  fi
}
AWS=(aws --profile "$AWS_PROFILE" --region "$AWS_REGION" --output json --no-cli-pager)
# Account-wide metadata only; nothing here marks a resource safe to delete.
emit instances ec2 describe-instances --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Volumes:BlockDeviceMappings[].Ebs.VolumeId,Tags:Tags}'
emit volumes ec2 describe-volumes --query 'Volumes[].{Id:VolumeId,State:State,Size:Size,Attachments:Attachments,Tags:Tags}'
emit load-balancers elbv2 describe-load-balancers --query 'LoadBalancers[].{Arn:LoadBalancerArn,Name:LoadBalancerName,State:State.Code,Vpc:VpcId}'
emit nat-gateways ec2 describe-nat-gateways --query 'NatGateways[].{Id:NatGatewayId,State:State,Vpc:VpcId,Tags:Tags}'
emit addresses ec2 describe-addresses --query 'Addresses[].{Id:AllocationId,Association:AssociationId,Instance:InstanceId,IP:PublicIp,Tags:Tags}'
emit snapshots ec2 describe-snapshots --owner-ids self --query 'Snapshots[].{Id:SnapshotId,Volume:VolumeId,Size:VolumeSize,State:State,Created:StartTime,Tags:Tags}'
emit images ec2 describe-images --owners self --query 'Images[].{Id:ImageId,Name:Name,State:State,Snapshots:BlockDeviceMappings[].Ebs.SnapshotId}'
if [[ -n "$OUTPUT" ]]; then python3 scripts/inventory_report.py "$OUTPUT"; fi
