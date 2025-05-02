# S3 Bucket Component

This Terraform component provisions a general-purpose Amazon S3 bucket with optional versioning, encryption, and public access blocking. It is designed to be driven entirely by config and deployed via the Adage framework using Terragrunt.

---

## Features

- Creates an S3 bucket with a configurable name
- Optional versioning and server-side encryption
- Option to block all public access
- Writes runtime values to SSM Parameter Store
- Supports standard tagging and force-destroy behavior

---

## Usage

Deploy with:

```bash
AWS_PROFILE=prod-iac ./scripts/deploy.sh s3-bucket karma-api --auto-approve
```

This will:

1. Read config from: `/iac/s3-bucket/karma-api/config`
2. Create an S3 bucket with the specified settings
3. Store runtime output in: `/iac/s3-bucket/karma-api/runtime`

---

## Required Inputs (`/iac/s3-bucket/<nickname>/config`)

```json
{
  "bucket_name": "usekarma.dev-prod-karma-api",
  "acl": "private",
  "versioning": true,
  "force_destroy": true,
  "enable_encryption": true,
  "sse_algorithm": "AES256",
  "block_public_access": true,
  "tags": {
    "Project": "karma"
  }
}
```

### Notes:
- `bucket_name` must be globally unique across all AWS accounts.
- `acl` is optional and defaults to `"private"` but is ignored if public access is blocked.
- `force_destroy` allows Terraform to delete the bucket even if it contains objects.
- `enable_encryption` enables server-side encryption (e.g., `"AES256"` or `"aws:kms"`).
- `block_public_access` is highly recommended for all non-website buckets.

---

## Outputs (`/iac/s3-bucket/<nickname>/runtime`)

```json
{
  "bucket_name": "usekarma.dev-prod-karma-api"
}
```

This value can be referenced by other components or deployment scripts (e.g., to publish an OpenAPI spec).

---

## How It Works

- Tags and lifecycle options are driven entirely by SSM config
- Defaults are safe (versioning on, public access blocked, encryption on)
- The component makes no assumptions about how the bucket will be used — it's generic and reusable

---

## Example Use Case

To publish an OpenAPI spec from a separate repository:

1. Create a `s3-bucket` config with `bucket_name = "usekarma.dev-prod-karma-api"`
2. Deploy the bucket via `./scripts/deploy.sh s3-bucket karma-api`
3. Upload `karma-api.yaml` to that bucket and record the location in `/iac/openapi/karma-api/runtime`

---

## Notes

- Avoid using the same `bucket_name` across environments unless intentionally shared
- This module does not include CloudFront or website hosting logic (see `serverless-site` for that)
- Bucket deletion requires `force_destroy: true` and no active object lock
