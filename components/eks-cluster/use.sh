#!/bin/bash
set -e

NICKNAME=$1

if [ -z "$NICKNAME" ]; then
  echo "Usage: $0 <nickname>"
  exit 1
fi

BASE_PATH="/iac/eks-cluster/$NICKNAME/runtime"

CLUSTER_NAME=$(aws ssm get-parameter --name "$BASE_PATH/cluster_name" --query 'Parameter.Value' --output text)
REGION=$(aws ssm get-parameter --name "$BASE_PATH/region" --query 'Parameter.Value' --output text)

echo "Using cluster: $CLUSTER_NAME ($REGION)"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"
