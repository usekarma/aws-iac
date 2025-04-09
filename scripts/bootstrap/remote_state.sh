#!/bin/bash
set -euo pipefail

# Ensure AWS_PROFILE is set
if [[ -z "${AWS_PROFILE:-}" ]]; then
  echo "❌ AWS_PROFILE must be set (e.g. export AWS_PROFILE=dev-iac)"
  exit 1
fi

# Get current AWS account and region
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
REGION=$(aws configure get region --profile "$AWS_PROFILE")

if [[ -z "$REGION" ]]; then
  echo "❌ No region configured for AWS_PROFILE='$AWS_PROFILE'."
  echo "👉 Run: aws configure --profile $AWS_PROFILE"
  exit 1
fi

# Define names
S3_BUCKET="${ACCOUNT_ID}-tf-state"
DDB_TABLE="${ACCOUNT_ID}-tf-locks"

echo "🔍 Bootstrapping remote state in account: $ACCOUNT_ID"
echo "   Region:          $REGION"
echo "   S3 Bucket:       $S3_BUCKET"
echo "   DynamoDB Table:  $DDB_TABLE"
echo

# Create S3 bucket if it doesn't exist
if aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  echo "✅ S3 bucket already exists: $S3_BUCKET"
else
  echo "📦 Creating S3 bucket: $S3_BUCKET"
  if [[ "$REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$S3_BUCKET"
  else
    aws s3api create-bucket \
      --bucket "$S3_BUCKET" \
      --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi

  echo "🔁 Enabling versioning on S3 bucket..."
  aws s3api put-bucket-versioning \
    --bucket "$S3_BUCKET" \
    --versioning-configuration Status=Enabled

  echo "🔒 Enabling server-side encryption..."
  aws s3api put-bucket-encryption \
    --bucket "$S3_BUCKET" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }]
    }'

  echo "🧹 Setting lifecycle rules for cleanup..."
  aws s3api put-bucket-lifecycle-configuration \
    --bucket "$S3_BUCKET" \
    --lifecycle-configuration '{
      "Rules": [
        {
          "ID": "ExpireOldVersions",
          "Filter": {},
          "Status": "Enabled",
          "NoncurrentVersionExpiration": { "NoncurrentDays": 90 }
        },
        {
          "ID": "AbortIncompleteMultipartUpload",
          "Filter": {},
          "Status": "Enabled",
          "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
        }
      ]
    }'
fi

# Tag S3 bucket (idempotent)
echo "🏷️  Tagging S3 bucket..."
aws s3api put-bucket-tagging \
  --bucket "$S3_BUCKET" \
  --tagging '{
    "TagSet": [
      { "Key": "Project", "Value": "aws-iac" },
      { "Key": "ManagedBy", "Value": "remote_state.sh" }
    ]
  }'

# Create DynamoDB table if it doesn't exist
if aws dynamodb describe-table --table-name "$DDB_TABLE" --region "$REGION" >/dev/null 2>&1; then
  echo "✅ DynamoDB table already exists: $DDB_TABLE"
else
  echo "🔒 Creating DynamoDB lock table: $DDB_TABLE"
  aws dynamodb create-table \
    --table-name "$DDB_TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"

  echo "⌛ Waiting for DynamoDB table to become active..."
  aws dynamodb wait table-exists --table-name "$DDB_TABLE" --region "$REGION"
fi

# Tag DynamoDB table
echo "🏷️  Tagging DynamoDB table..."
aws dynamodb tag-resource \
  --resource-arn "arn:aws:dynamodb:$REGION:$ACCOUNT_ID:table/$DDB_TABLE" \
  --tags Key=Project,Value=aws-iac Key=ManagedBy,Value=remote_state.sh

echo
echo "✅ Remote state bootstrap complete for account: $ACCOUNT_ID"
