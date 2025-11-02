# Cluster Component

This component provisions an **ECS Cluster** using Adage conventions:
- Reads configuration from SSM Parameter Store  
- Publishes a **runtime parameter** for downstream components (like `ecs-service`)

It’s fully **config-driven**, with no hard-coded networking or service definitions.

---

## 📁 Parameter Store Paths

| Purpose | Path Pattern | Description |
|----------|---------------|--------------|
| Config | `/iac/ecs-cluster/<nickname>/config` | Cluster configuration JSON |
| VPC Runtime | `/iac/vpc/<vpc_nickname>/runtime` | VPC networking metadata (read-only) |
| Cluster Runtime | `/iac/ecs-cluster/<nickname>/runtime` | Published output JSON for services |

---

## 🧩 Example Config

### `/iac/ecs-cluster/core/config`
```json
{
  "cluster_name": "core-ecs",
  "vpc_nickname": "core",
  "enable_execute_command": true,
  "exec_logging": "OVERRIDE",
  "create_log_group": true,
  "log_retention_days": 14,
  "enable_container_insights": true,
  "capacity_providers": ["FARGATE", "FARGATE_SPOT"],
  "default_capacity_strategy": [
    {"capacity_provider": "FARGATE", "weight": 1},
    {"capacity_provider": "FARGATE_SPOT", "weight": 1}
  ],
  "tags": {
    "Project": "usekarma",
    "Component": "ecs-cluster",
    "Environment": "dev",
    "Owner": "ted.strall"
  }
}
```

This config must exist in SSM **before** you `terraform apply`.

---

## 🏗️ What This Component Creates

| Type | Name | Description |
|------|------|--------------|
| `aws_ecs_cluster` | `this` | ECS Cluster with optional Exec + Container Insights |
| `aws_cloudwatch_log_group` | `this` | Optional log group for ECS Exec |
| `aws_ecs_cluster_capacity_providers` | `this` | Optional capacity providers & default strategy |
| `aws_ssm_parameter` | `runtime` | JSON-encoded runtime info for `ecs-service` components |

---

## 🪣 Runtime Parameter Schema

### `/iac/ecs-cluster/<nickname>/runtime`

After apply, the ECS Cluster writes a minimal JSON payload for service consumers:

```json
{
  "cluster_arn": "arn:aws:ecs:us-east-1:123456789012:cluster/core-ecs",
  "cluster_name": "core-ecs",
  "capacity_providers": ["FARGATE", "FARGATE_SPOT"],
  "default_capacity_strategy": [
    {"capacity_provider": "FARGATE", "weight": 1},
    {"capacity_provider": "FARGATE_SPOT", "weight": 1}
  ]
}
```

This parameter is **idempotently updated** (`overwrite = true`) and tagged consistently.

---

## 🧠 Design Notes

- Follows Adage pattern: all inputs from SSM, all outputs to SSM.
- No direct VPC or ECS service creation — those belong to separate components.
- `ecs-service` components will read the `/iac/ecs-cluster/<nick>/runtime` JSON at runtime to discover the cluster ARN and placement strategy.

---

## 🧪 Example Usage

```hcl
module "ecs_cluster" {
  source   = "../../modules/ecs-cluster"
  nickname = "core"
}
```

Then:
```bash
terraform init
terraform apply -auto-approve
```

---

# 🔄 Example: ecs-service Consumer Component

A service component typically consumes two runtime parameters:
- `/iac/ecs-cluster/<nick>/runtime` — for ECS cluster metadata
- `/iac/vpc/<nick>/runtime` — for networking context

### Example: `/iac/ecs-service/api/config`
```json
{
  "cluster_nickname": "core",
  "vpc_nickname": "core",
  "service_name": "api",
  "container_image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/api:latest",
  "desired_count": 2,
  "cpu": 512,
  "memory": 1024,
  "container_port": 8080,
  "assign_public_ip": false,
  "load_balancer": {
    "target_group_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/api/abcdef"
  }
}
```

### ecs-service module (simplified)
```hcl
data "aws_ssm_parameter" "cluster_runtime" {
  name = "/iac/ecs-cluster/${var.cluster_nickname}/runtime"
}

data "aws_ssm_parameter" "vpc_runtime" {
  name = "/iac/vpc/${var.vpc_nickname}/runtime"
}

locals {
  cluster = jsondecode(data.aws_ssm_parameter.cluster_runtime.value)
  vpc     = jsondecode(data.aws_ssm_parameter.vpc_runtime.value)
}

resource "aws_ecs_service" "this" {
  name            = var.service_name
  cluster         = local.cluster.cluster_arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = local.vpc.private_subnet_ids
    security_groups  = [local.vpc.default_security_group_id]
    assign_public_ip = false
  }
  task_definition = aws_ecs_task_definition.this.arn
}
```

This pattern ensures every component — cluster, service, or VPC — is declaratively linked through SSM metadata rather than direct Terraform references.

---

© 2025 usekarma.dev — Adage Infrastructure Components
