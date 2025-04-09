## 📁 `scripts/` — Project Utilities

This directory contains utility scripts that support bootstrapping and managing your Terraform-based AWS infrastructure. These scripts are designed to be **safe**, **reusable**, and **compatible with your multi-account, multi-environment setup**.

---

### 📜 Scripts Included

#### 🛠️ `bootstrap/remote_state.sh`

Bootstraps the required Terraform remote state resources for the current AWS account.

**What it does:**
- Creates an S3 bucket for Terraform state (`<account_id>-tf-state`) if it doesn't exist
- Creates a DynamoDB table for Terraform locking (`<account_id>-tf-locks`) if it doesn't exist
- Enables versioning on the S3 bucket
- Uses the region configured in the active AWS CLI profile

**Usage:**
```bash
AWS_PROFILE=dev-iac ./scripts/bootstrap/remote_state.sh
```

You can safely run this script multiple times — it's idempotent.

---

#### 🧹 `clean.sh`

Removes all local Terraform build artifacts to ensure a clean working state.

**What it cleans:**
- `.terragrunt-work/` (isolated per-run directories)
- `.terraform/`, `.terraform.lock.hcl`, and `terraform.tfstate*` if present in the root
- `crash.log` (Terraform error dump)

**Usage:**
```bash
./scripts/clean.sh
```

Use this after experimentation or before committing to clear local artifacts.

---

### 🔐 Assumptions

These scripts assume:
- You’ve configured AWS CLI profiles (`~/.aws/config` and `~/.aws/credentials`)
- Each profile includes a default `region` (`aws configure --profile <name>`)
- You’re using a single control region per account (e.g., `us-east-1`)
