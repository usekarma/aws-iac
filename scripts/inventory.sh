#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
./scripts/preflight.sh
AWS=(aws --profile "$AWS_PROFILE" --region "$AWS_REGION" --output json --no-cli-pager)
# Account-wide metadata only; nothing here marks a resource safe to delete.
"${AWS[@]}" ec2 describe-instances --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Volumes:BlockDeviceMappings[].Ebs.VolumeId,Tags:Tags}'
"${AWS[@]}" ec2 describe-volumes --query 'Volumes[].{Id:VolumeId,State:State,Size:Size,Attachments:Attachments,Tags:Tags}'
"${AWS[@]}" elbv2 describe-load-balancers --query 'LoadBalancers[].{Arn:LoadBalancerArn,Name:LoadBalancerName,State:State.Code,Vpc:VpcId}'
"${AWS[@]}" ec2 describe-nat-gateways --query 'NatGateways[].{Id:NatGatewayId,State:State,Vpc:VpcId,Tags:Tags}'
"${AWS[@]}" ec2 describe-addresses --query 'Addresses[].{Id:AllocationId,Association:AssociationId,Instance:InstanceId,IP:PublicIp,Tags:Tags}'
"${AWS[@]}" ec2 describe-snapshots --owner-ids self --query 'Snapshots[].{Id:SnapshotId,Volume:VolumeId,Size:VolumeSize,State:State,Created:StartTime,Tags:Tags}'
"${AWS[@]}" ec2 describe-images --owners self --query 'Images[].{Id:ImageId,Name:Name,State:State,Snapshots:BlockDeviceMappings[].Ebs.SnapshotId}'
