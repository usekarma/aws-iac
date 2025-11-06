#!/usr/bin/env bash
# Build and push the clickhouse-kconnect-jmx-exporter image to ECR

set -euo pipefail

# --- Config --------------------------------------------------------------
REGION="us-east-1"
REPO_NAME="clickhouse-kconnect-jmx-exporter"

# --- Discover account id -------------------------------------------------
echo "[build.sh] Fetching AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_URI="${ECR_REGISTRY}/${REPO_NAME}:latest"

echo "[build.sh] Using account: ${ACCOUNT_ID}"
echo "[build.sh] Target image: ${ECR_URI}"

# --- Ensure ECR repo exists ----------------------------------------------
echo "[build.sh] Ensuring ECR repository '${REPO_NAME}' exists..."
if ! aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${REGION}" >/dev/null 2>&1; then
  echo "[build.sh] Repository not found. Creating..."
  aws ecr create-repository --repository-name "${REPO_NAME}" --region "${REGION}" >/dev/null
  echo "[build.sh] Repository created."
else
  echo "[build.sh] Repository already exists."
fi

# --- Build image ---------------------------------------------------------
echo "[build.sh] Building Docker image..."
docker build -t "${ECR_URI}" .

# --- Login to ECR --------------------------------------------------------
echo "[build.sh] Logging into ECR..."
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# --- Push image ----------------------------------------------------------
echo "[build.sh] Pushing image to ${ECR_URI} ..."
docker push "${ECR_URI}"

echo "[build.sh] Done!"
echo "Image pushed: ${ECR_URI}"
echo
echo "Next step: add this to your SSM config JSON:"
echo
echo "  \"kconnect_metrics_image\": \"${ECR_URI}\""
