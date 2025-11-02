# ECS Service Component

This component creates an **ECS Service (Fargate)** by reading all inputs from SSM:

- Service config: `/iac/ecs-service/<nickname>/config` (JSON)
- Cluster runtime: `/iac/ecs-cluster/<cluster_nickname>/runtime` (JSON)
- VPC runtime: `/iac/vpc/<vpc_nickname>/runtime` (JSON)

It also publishes its own runtime to:
- `/iac/ecs-service/<nickname>/runtime`

## Expected Config JSON

### `/iac/ecs-service/api/config`
```json
{
  "cluster_nickname": "core",
  "vpc_nickname": "core",
  "service_name": "api",
  "desired_count": 2,
  "cpu": 512,
  "memory": 1024,
  "platform_version": "LATEST",
  "assign_public_ip": false,
  "container": {
    "name": "api",
    "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/api:latest",
    "port": 8080,
    "environment": [
      {"name": "ENV", "value": "dev"}
    ],
    "secrets": [
      {"name": "DB_PASSWORD", "valueFrom": "arn:aws:ssm:us-east-1:123456789012:parameter/app/db/password"}
    ],
    "log_group_retention_days": 14
  },
  "load_balancer": {
    "target_group_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/api/abcdef"
  },
  "security_groups": [],
  "tags": {
    "Project": "usekarma",
    "Component": "ecs-service",
    "Service": "api",
    "Environment": "dev"
  }
}
```
Notes:
- If `security_groups` is omitted or empty, the module will use the VPC **default_security_group_id** from `/iac/vpc/<nick>/runtime`.
- If `load_balancer.target_group_arn` is provided, the service will register the container/port to that TG.

## What This Component Creates
- `aws_iam_role.task_execution` + minimal policy attachment
- `aws_iam_role.task` (empty permissions by default)
- `aws_cloudwatch_log_group.this` (optional; enabled automatically when a container is defined)
- `aws_ecs_task_definition.this`
- `aws_ecs_service.this` (Fargate)
- `aws_ssm_parameter.runtime` published at `/iac/ecs-service/<nickname>/runtime`

The ECS Cluster and VPC are **not** created here; they are read-only dependencies via SSM.

## Module Input
- `nickname` (string) — the service nickname used to resolve SSM paths.

## Outputs
- `service_name`, `service_arn`, `task_definition_arn`, `runtime_path`

## Example
See `examples/api-service/`.

© 2025 usekarma.dev — Adage Infrastructure Components
