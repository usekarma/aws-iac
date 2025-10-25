#!/bin/bash
set -euo pipefail

# ------------------------
# Usage:
#   AWS_PROFILE=dev ./deploy.sh serverless-site marketing-site
#   AWS_PROFILE=prod ./deploy.sh --destroy serverless-site docs-site --auto-approve
#   AWS_PROFILE=dev ./deploy.sh --plan serverless-site docs-site
#   AWS_PROFILE=dev ./deploy.sh --validate serverless-site docs-site
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
    --plan)
      ACTION="plan"
      shift
      ;;
    --validate)
      ACTION="validate"
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

if [[ -z "${COMPONENT:-}" || -z "${NICKNAME:-}" ]]; then
  echo "❌ Usage:"
  echo "   AWS_PROFILE=dev ./scripts/deploy.sh serverless-site marketing-site [--auto-approve]"
  echo "   AWS_PROFILE=prod ./scripts/deploy.sh --destroy serverless-site docs-site [--auto-approve]"
  echo "   AWS_PROFILE=dev ./scripts/deploy.sh --plan serverless-site docs-site"
  echo "   AWS_PROFILE=dev ./scripts/deploy.sh --validate serverless-site docs-site"
  exit 1
fi

# Set dynamic inputs
export TF_COMPONENT="$COMPONENT"
export TF_NICKNAME="$NICKNAME"
export TF_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
export TF_REGION=$(aws configure get region)

# Set isolated working directory
WORKDIR=".terragrunt-work/${TF_ACCOUNT_ID}/${COMPONENT}/${NICKNAME}"
mkdir -p "$WORKDIR"
cp terragrunt.hcl "$WORKDIR/"

echo "🚀 Running terragrunt $ACTION"
echo "   Component:   $COMPONENT"
echo "   Nickname:    $NICKNAME"
echo "   AWS Profile: $AWS_PROFILE"
echo "   AWS Account: $TF_ACCOUNT_ID"
echo "   AWS Region:  $TF_REGION"
echo "   Working Dir: $WORKDIR"
echo

# Add --non-interactive if --auto-approve is used
NON_INTERACTIVE_FLAGS=()
if [[ "${EXTRA_ARGS[*]}" =~ "--auto-approve" ]]; then
  NON_INTERACTIVE_FLAGS+=(--non-interactive)
fi

# Temporary override
NON_INTERACTIVE_FLAGS+=(--non-interactive)

# Terragrunt init (safe for all actions)
terragrunt init --all \
  --working-dir "$WORKDIR" \
  "${NON_INTERACTIVE_FLAGS[@]}"

# Main command
terragrunt "$ACTION" --all \
  --working-dir "$WORKDIR" \
  "${EXTRA_ARGS[@]}" \
  "${NON_INTERACTIVE_FLAGS[@]}"
