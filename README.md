# AWS Infrastructure as Code (IaC)

## Overview

This repository contains reusable **Terraform modules** for deploying AWS infrastructure **dynamically** based on configurations stored in AWS Parameter Store.

### Key Features

- **Decouples infrastructure from deployment** – Terraform only deploys what’s pre-approved in the config repo.
- **No hardcoded environments** – Everything is dynamically resolved at runtime.
- **Uses AWS Parameter Store for configurations** – Ensures deployments are controlled via Git.
- **Integrates with `aws-config` and `aws-lambda`** – Supports a fully configuration-driven AWS deployment model.

---

## Repository Structure

```
aws-iac/
├── components/
│   ├── vpc/               # Reusable VPC module
│   ├── aurora-postgres/   # Reusable Aurora RDS module
│   └── ...
├── modules/
├── README.md
```

---

## How It Works

### 1. Requires Predefined Configuration

Terraform does not deploy anything unless configuration already exists in AWS Parameter Store.  
All configuration is authored and version-controlled in the [`aws-config`](https://github.com/tstrall/aws-config) repository.

For example, to deploy a VPC with the nickname `main-vpc`, Terraform looks for:

```
/iac/vpc/main-vpc/config      # Must exist before apply
/iac/vpc/main-vpc/runtime     # Created after deployment
```

If the config is missing, Terraform will fail with a validation error.

### 2. Deploys Only Pre-Approved Components

Once the config is found, Terraform proceeds with deployment and publishes the runtime metadata.

```bash
terraform init
terraform apply -var="nickname=main-vpc"
```

---

## Example: Deploying a VPC

### 1. Define the VPC Configuration (in `aws-config`)

```json
{
  "vpc_cidr": "10.0.0.0/16",
  "enable_dns_support": true,
  "private_subnet_cidrs": ["10.0.1.0/24", "10.0.2.0/24"]
}
```

This config must be stored in Parameter Store at `/iac/vpc/main-vpc/config`.

### 2. Deploy the VPC Using Terraform

```bash
terraform apply -var="nickname=main-vpc"
```

### 3. Runtime Info Is Registered Automatically

After deployment, Terraform stores runtime metadata at:

```
/iac/vpc/main-vpc/runtime     # Contains VPC ID, subnet IDs, etc.
```

Other modules can consume this runtime info without referencing Terraform state.

---

## Dynamic Dependency Resolution

Each deployed component publishes its runtime configuration to Parameter Store.  
Dependent components can dynamically resolve what they need using native Terraform lookups.

Example:

```hcl
data "aws_ssm_parameter" "vpc_runtime" {
  name = "/iac/vpc/main-vpc/runtime"
}

locals {
  vpc_details = jsondecode(data.aws_ssm_parameter.vpc_runtime.value)
}
```

This removes the need for shared state or explicit module dependencies.

---

## Security and Governance

- **Prevents unauthorized deployments** – Only pre-approved configurations can be applied.
- **Enforces auditability** – All infrastructure is version-controlled via Git.
- **Supports secure secrets** – Sensitive values can be stored in AWS Secrets Manager and referenced during deployment.

---

## Project Background

This repository is part of a broader open-source deployment framework focused on configuration-driven infrastructure in AWS.

It is developed independently as part of a modular, extensible architecture designed to support long-term maintainability, auditability, and reuse.

For a complete overview, see the [aws-deployment-guide](https://github.com/tstrall/aws-deployment-guide).

---

## Next Steps

To adopt this in your own environment:

1. Fork this repo and define your own components.
2. Use `aws-config` to manage deployment inputs.
3. Integrate with CI/CD to automate validation and deployment workflows.

