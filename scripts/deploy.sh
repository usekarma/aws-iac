#!/bin/bash
set -euo pipefail

# Requires independently reviewed target variables; see scripts/README.md.
# Safe entrypoint: ./scripts/plan.sh COMPONENT NICKNAME [--destroy]
# Default action is apply and requires explicit human approval.

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ACTION="apply"
DESTROY_PLAN=0
EXTRA_ARGS=()
AUTO_APPROVE=0
PLAN_CONFIG=""

# Parse flags and arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-config)
      [[ $# -ge 2 ]] || { echo "--plan-config requires a JSON file" >&2; exit 1; }
      PLAN_CONFIG="$2"
      shift 2
      ;;
    -d|--destroy)
      ACTION="destroy"
      shift
      ;;
    --plan)
      ACTION="plan"
      shift
      ;;
    --destroy-plan)
      ACTION="plan"
      DESTROY_PLAN=1
      shift
      ;;
    --validate)
      ACTION="validate"
      shift
      ;;
    --auto-approve)
      AUTO_APPROVE=1
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

if [[ -n "$PLAN_CONFIG" ]]; then
  [[ "$ACTION" == "plan" && "$DESTROY_PLAN" == "0" && "${COMPONENT:-}" == "s3-bucket" ]] || { echo "--plan-config is only supported for s3-bucket creation plans" >&2; exit 1; }
  [[ -f "$PLAN_CONFIG" ]] || { echo "Plan config file does not exist" >&2; exit 1; }
  PLAN_CONFIG_JSON=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "$PLAN_CONFIG")
  EXTRA_ARGS+=("-var=plan_config_json=$PLAN_CONFIG_JSON")
fi

# Agent mode cannot be overridden by a human acknowledgement in the environment.
if [[ "${AGENT_MODE:-0}" != "0" && "${AGENT_MODE:-0}" != "1" ]]; then
  echo "AGENT_MODE must be 0 or 1" >&2; exit 1
fi
if [[ "${AGENT_MODE:-0}" == "1" && ( "$ACTION" != "plan" && "$ACTION" != "validate" || "$AUTO_APPROVE" == "1" ) ]]; then
  echo "AGENT_MODE=1 blocks apply, destroy and auto-approve. Use scripts/plan.sh or --validate; execution requires a separately approved human path." >&2
  exit 1
fi

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

# Identity, environment and target must be independently reviewed.
[[ "$COMPONENT" =~ ^[a-z0-9-]+$ && "$NICKNAME" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo "Invalid component/nickname" >&2; exit 1; }
[[ -f "components/$COMPONENT/header.tf" ]] || { echo "No deployable component: $COMPONENT" >&2; exit 1; }
python3 - "$COMPONENT" <<'PY_STATUS'
import json, pathlib, sys
status = json.loads(pathlib.Path("components/status.json").read_text()).get(sys.argv[1], {})
if status.get("status") == "incomplete":
    sys.exit("Blocked incomplete component: " + status["reason"])
PY_STATUS
if [[ "$ACTION" == "apply" || "$ACTION" == "destroy" ]]; then
  [[ "${AWS_MUTATION_APPROVED:-}" == "1" ]] || { echo "Explicit human approval required; see AGENTS.md" >&2; exit 1; }
elif [[ "$AUTO_APPROVE" == "1" ]]; then
  echo "--auto-approve is valid only for approved apply/destroy" >&2
  exit 1
fi
IAC_PREFLIGHT_COMPONENT="$COMPONENT" ./scripts/preflight.sh
# Reject identity/argument overrides that could diverge from the reviewed target.
while IFS= read -r variable; do
  case "$variable" in
    TF_DATA_DIR|TF_WORKSPACE|TF_VAR_*|TF_CLI_ARGS*|TG_IAM_ASSUME_ROLE*|TERRAGRUNT_IAM_ROLE*|TG_AUTH_PROVIDER_CMD|TERRAGRUNT_AUTH_PROVIDER_CMD)
      [[ -z "${!variable}" ]] || { echo "Unset $variable before repository deployment commands" >&2; exit 1; }
      ;;
  esac
done < <(compgen -e)
export TF_COMPONENT="$COMPONENT" TF_NICKNAME="$NICKNAME"
export TF_ACCOUNT_ID="$EXPECTED_AWS_ACCOUNT" TF_REGION="$AWS_REGION"
export AWS_DEFAULT_REGION="$AWS_REGION" AWS_PAGER="" TG_TF_PATH=terraform

# Planning must not bootstrap/update remote state infrastructure.
unset TG_BACKEND_BOOTSTRAP TG_ALL TG_NON_INTERACTIVE TG_CONFIG TG_WORKING_DIR
unset TERRAGRUNT_ALL TERRAGRUNT_NON_INTERACTIVE TERRAGRUNT_CONFIG TERRAGRUNT_WORKING_DIR
SAFE_FLAGS=(--backend-require-bootstrap --disable-bucket-update)
if [[ "$ACTION" == "plan" || "$ACTION" == "validate" ]]; then
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" s3api head-bucket --bucket "${TF_ACCOUNT_ID}-tf-state" --expected-bucket-owner "$TF_ACCOUNT_ID"
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" dynamodb describe-table --table-name "${TF_ACCOUNT_ID}-tf-locks" --query Table.TableStatus --output text
fi
if [[ "$ACTION" == "plan" ]]; then
  EXTRA_ARGS+=(-input=false -lock=false -out=review.tfplan)
  if [[ "$DESTROY_PLAN" == "1" ]]; then EXTRA_ARGS+=(-destroy); fi
fi

# Set isolated working directory
WORKDIR=".terragrunt-work/${TF_ACCOUNT_ID}/${COMPONENT}/${NICKNAME}"
umask 077
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

# Non-interactive mode is limited to inspection; mutations keep native confirmation
# unless the already-approved human operator explicitly selected --auto-approve.
NON_INTERACTIVE_FLAGS=()
if [[ "$ACTION" == "plan" || "$ACTION" == "validate" || "${EXTRA_ARGS[*]}" == *--auto-approve* ]]; then
  NON_INTERACTIVE_FLAGS+=(--non-interactive)
fi
# This wrapper selects exactly one unit; --all would silently add auto-approval.
terragrunt init --working-dir "$WORKDIR" "${SAFE_FLAGS[@]}" "${NON_INTERACTIVE_FLAGS[@]}"
terragrunt "$ACTION" --working-dir "$WORKDIR" "${SAFE_FLAGS[@]}" "${EXTRA_ARGS[@]}" "${NON_INTERACTIVE_FLAGS[@]}"
if [[ "$ACTION" == "plan" ]]; then
  echo "Private plan saved as review.tfplan in the component's Terragrunt cache under $WORKDIR."
  echo "Review with terraform show from that cache; digest with sha256sum. No approval is granted."
fi
