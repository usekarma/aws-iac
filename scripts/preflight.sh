#!/usr/bin/env bash
set -euo pipefail
: "${AWS_PROFILE:?Set a named AWS_PROFILE}"
: "${AWS_REGION:?Set the reviewed AWS_REGION}"
: "${EXPECTED_AWS_ACCOUNT:?Set the reviewed 12-digit account ID}"
: "${EXPECTED_ENVIRONMENT:?Set the environment type, e.g. prod or dev}"
: "${EXPECTED_BINDING:?Set the exact binding name, e.g. usekarma-dev-prod}"
[[ "$EXPECTED_AWS_ACCOUNT" =~ ^[0-9]{12}$ ]] || { echo "Invalid account ID" >&2; exit 1; }
[[ "$AWS_REGION" =~ ^[a-z]{2}(-[a-z]+)+-[0-9]+$ ]] || { echo "Invalid region" >&2; exit 1; }
[[ "${IAC_PREFIX:-/iac}" =~ ^(/[a-zA-Z0-9_-]+)+$ ]] || { echo "Invalid IAC_PREFIX; use an absolute path without trailing slash" >&2; exit 1; }
# Avoid identity divergence between the AWS CLI and Terraform/provider SDKs.
for variable in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_WEB_IDENTITY_TOKEN_FILE AWS_ROLE_ARN AWS_CONTAINER_CREDENTIALS_RELATIVE_URI AWS_CONTAINER_CREDENTIALS_FULL_URI; do
  [[ -z "${!variable:-}" ]] || { echo "Unset $variable; use only the named profile" >&2; exit 1; }
done
export AWS_DEFAULT_REGION="$AWS_REGION" AWS_PAGER=""
account=$(aws --profile "$AWS_PROFILE" --region "$AWS_REGION" sts get-caller-identity --query Account --output text)
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "AWS account mismatch; refusing to continue" >&2; exit 1; }
binding=$(aws --profile "$AWS_PROFILE" --region "$AWS_REGION" ssm get-parameter --name "${IAC_PREFIX:-/iac}/environment" --query Parameter.Value --output text)
printf '%s' "$binding" | python3 -c 'import json,os,sys; b=json.load(sys.stdin); sys.exit(0 if b.get("name")==os.environ["EXPECTED_BINDING"] and b.get("environment")==os.environ["EXPECTED_ENVIRONMENT"] else "Environment binding mismatch; refusing to continue")'
printf 'Verified profile=%s account=%s region=%s environment=%s binding=%s prefix=%s\n' "$AWS_PROFILE" "$account" "$AWS_REGION" "$EXPECTED_ENVIRONMENT" "$EXPECTED_BINDING" "${IAC_PREFIX:-/iac}"
