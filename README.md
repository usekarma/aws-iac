# AWS Infrastructure as Code (IaC)

## Overview

This repository contains reusable **Terraform modules** for deploying AWS infrastructure **dynamically** based on configurations stored in AWS Parameter Store.

For a complete overview, see [Adage: AWS Deployment Framework](https://github.com/usekarma/adage).

---

### Key Features

- **Decouples infrastructure from deployment** – Terraform only deploys what’s pre-approved in the config repo.
- **No hardcoded environments** – Everything is dynamically resolved at runtime.
- **Uses AWS Parameter Store for configurations** – Ensures deployments are controlled via Git.
- **Supports dynamic runtime resolution** – No Terraform state sharing required across modules.
- **Configurable prefix (`/iac`)** – Set `IAC_PREFIX` to change Parameter Store paths across the entire stack.
- **Integrates with `aws-config` and `aws-lambda`** – Enables a fully configuration-driven AWS deployment model.

---

## Repository Structure

```
aws-iac/
├── components/
│   ├── vpc/               # Reusable VPC module
│   ├── aurora-postgres/   # Reusable Aurora RDS module
│   └── ...
├── scripts/
│   └── deploy.sh          # Terragrunt-based wrapper for deploying individual components
├── terragrunt.hcl         # Root configuration for remote state + inputs
├── README.md
```

---

## Developer Setup: AWS CLI + Prompt Customization

This framework uses named AWS CLI profiles to authenticate into different AWS accounts.

To configure AWS SSO and optionally customize your shell prompt for safety and visibility, see:

📄 [`setup/bash-aws-profile-prompt.md`](https://github.com/usekarma/adage/blob/main/setup/bash-aws-profile-prompt.md)

---

## How It Works

### 1. Configuration Must Already Exist

Terraform will not deploy anything unless configuration has already been published to AWS Parameter Store.

All configuration is authored and version-controlled in the [`aws-config`](https://github.com/usekarma/aws-config) repository and published using approved scripts.

For example, to deploy a VPC with the nickname `main-vpc`, the following must exist:

```
/iac/vpc/main-vpc/config      # Deployment input (set manually)
/iac/vpc/main-vpc/runtime     # Deployment output (written by Terraform)
```

You can override the prefix (`/iac`) using `IAC_PREFIX`:

```bash
IAC_PREFIX=/karma AWS_PROFILE=dev ./scripts/deploy.sh vpc main-vpc
```

---

### 2. Deployment Uses `nickname` + `component`

Each deployable instance is referenced by its:

- **component name** (e.g., `vpc`, `aurora-postgres`)
- **nickname** (e.g., `main-vpc`, `default-db`)

The deploy wrapper passes these values into Terragrunt, which injects them as Terraform variables (`var.nickname`, `var.iac_prefix`, etc.).

---

## Example: Deploying a VPC

### 1. Define Configuration in `aws-config`

```json
{
  "vpc_cidr": "10.0.0.0/16",
  "enable_dns_support": true,
  "private_subnet_cidrs": ["10.0.1.0/24", "10.0.2.0/24"]
}
```

Published to:

```
/iac/vpc/main-vpc/config
```

---

### 2. Deploy the Component

```bash
AWS_PROFILE=dev ./scripts/deploy.sh vpc main-vpc
```

The script:

- Sets up the working directory
- Injects `nickname`, `iac_prefix`, and other Terragrunt variables
- Applies the corresponding component under `components/vpc`

---

### 3. Runtime Metadata Is Published

After deployment, Terraform writes runtime metadata to:

```
/iac/vpc/main-vpc/runtime
```

This includes:

- VPC ID
- Subnet IDs
- Tags and routing information

---

## Dynamic Dependency Resolution

All components publish their runtime state to Parameter Store.  
Other components can consume this without shared Terraform state.

Example:

```hcl
data "aws_ssm_parameter" "vpc_runtime" {
  name = "${var.iac_prefix}/vpc/main-vpc/runtime"
}

locals {
  vpc_details = jsondecode(data.aws_ssm_parameter.vpc_runtime.value)
}
```

This allows for completely dynamic and decoupled dependency graphs.

---

## Configuration Prefix: `IAC_PREFIX`

The prefix used in Parameter Store defaults to:

```
/iac
```

You can override this globally for any deploy:

```bash
IAC_PREFIX=/karma AWS_PROFILE=dev ./scripts/deploy.sh aurora-postgres default-db
```

Each Terraform module must accept `iac_prefix` as an input and use it in any Parameter Store lookups.

---

## Security and Governance

- **Prevents unauthorized changes** – Terraform fails if no config exists in Parameter Store
- **Enforces Git review** – All configuration is stored and approved via `aws-config`
- **Locks down environments** – IAM permissions can restrict Parameter Store access
- **Supports Secrets Manager** – Use for secure values alongside non-secret config

---

## Project Background

This repository is part of a broader open-source deployment framework focused on configuration-driven infrastructure in AWS.

It is maintained as part of the [Adage](https://github.com/usekarma/adage) project and supports scalable, multi-environment, multi-account architecture patterns.

---

## Next Steps

1. Fork this repo and define your own components under `components/`
2. Use [`aws-config`](https://github.com/usekarma/aws-config) to publish deployment inputs
3. Use `scripts/deploy.sh` to deploy components safely
4. Inject `IAC_PREFIX` as needed for alternate frameworks or naming schemes
