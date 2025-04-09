#!/bin/bash
set -euo pipefail

# ------------------------
# Usage:
#   AWS_PROFILE=dev ./deploy.sh serverless-site marketing-site
#   AWS_PROFILE=prod ./deploy.sh --destroy serverless-site docs-site --auto-approve
# ------------------------

ACTION="apply"
EXTRA_ARGS=()

# Parse flags and arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--destroy)
      ACTION="destroy"
      shift
      ;;
    --auto-approve)
      EXTRA_ARGS+=(--auto-approve)
      shift
      ;;
    -*)
      echo "❌ Unknown option: $1"
      exit 1
      ;;
    *)
      if [[ -z "${COMPONENT:-}" ]]; then
        COMPONENT="$1"
      elif [[ -z "${NICKNAME:-}" ]]; then
        NICKNAME="$1"
      else
        echo "❌ Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

# Validate AWS_PROFILE and arguments
if [[ -z "${AWS_PROFILE:-}" ]]; then
  echo "❌ Error: AWS_PROFILE must be set (e.g., export AWS_PROFILE=dev)"
  exit 1
fi

# Ensure region is configured in the AWS profile
REGION=$(aws configure get region --profile "$AWS_PROFILE" || true)
if [[ -z "$REGION" ]]; then
  echo "❌ Error: No region configured for AWS_PROFILE='$AWS_PROFILE'."
  echo "👉 Run: aws configure --profile $AWS_PROFILE"
  exit 1
fi

if [[ -z "${COMPONENT:-}" || -z "${NICKNAME:-}" ]]; then
  echo "❌ Usage:"
  echo "   AWS_PROFILE=dev ./deploy.sh serverless-site marketing-site [--auto-approve]"
  echo "   AWS_PROFILE=prod ./deploy.sh --destroy serverless-site docs-site [--auto-approve]"
  exit 1
fi

# Set dynamic inputs
export TF_COMPONENT="$COMPONENT"
export TF_NICKNAME="$NICKNAME"

# Create isolated working directory per run
WORKDIR=".terragrunt-work/${COMPONENT}-${NICKNAME}"
mkdir -p "$WORKDIR"
cp terragrunt.hcl "$WORKDIR/"

echo "🚀 Running terragrunt $ACTION"
echo "   Component:  $COMPONENT"
echo "   Nickname:   $NICKNAME"
echo "   AWS Profile: $AWS_PROFILE"
echo "   AWS Account: $(aws sts get-caller-identity --query 'Account' --output text)"
echo "   AWS Region:    $REGION"
echo "   Working Dir: $WORKDIR"
echo

# Run Terragrunt from the isolated directory
terragrunt run-all init \
  --terragrunt-working-dir "$WORKDIR"

terragrunt run-all "$ACTION" \
  --terragrunt-working-dir "$WORKDIR" \
  "${EXTRA_ARGS[@]}"
