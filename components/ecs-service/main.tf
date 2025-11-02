locals {
  cluster_nickname   = try(local.cfg.cluster_nickname, null)
  vpc_nickname       = try(local.cfg.vpc_nickname, null)

  service_name       = try(local.cfg.service_name, "svc-${var.nickname}")
  desired_count      = try(local.cfg.desired_count, 1)
  cpu                = try(local.cfg.cpu, 256)
  memory             = try(local.cfg.memory, 512)
  platform_version   = try(local.cfg.platform_version, "LATEST")
  assign_public_ip   = try(local.cfg.assign_public_ip, false)

  container          = try(local.cfg.container, {})
  container_name     = try(local.container.name, "app")
  container_image    = try(local.container.image, null)
  container_port     = try(local.container.port, null)
  container_env      = try(local.container.environment, [])
  container_secrets  = try(local.container.secrets, [])
  log_retention_days = try(local.container.log_group_retention_days, 14)

  lb                 = try(local.cfg.load_balancer, {})
  target_group_arn   = try(local.lb.target_group_arn, null)

  explicit_sgs       = try(local.cfg.security_groups, null)
}

locals {
  cluster = try(jsondecode(data.aws_ssm_parameter.cluster_runtime.value), {})
  cluster_arn = try(local.cluster.cluster_arn, null)
}

locals {
  vpc                       = try(jsondecode(data.aws_ssm_parameter.vpc_runtime.value), {})
  vpc_id                    = try(local.vpc.vpc_id, null)
  private_subnet_ids        = try(local.vpc.private_subnet_ids, null)
  public_subnet_ids         = try(local.vpc.public_subnet_ids, null)
  default_security_group_id = try(local.vpc.default_security_group_id, null)
  service_security_groups   = local.explicit_sgs != null && length(local.explicit_sgs) > 0 ? local.explicit_sgs : [local.default_security_group_id]
}

# ---------- IAM roles for task ----------
data "aws_iam_policy_document" "task_execution_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "task_execution" {
  name_prefix = "${local.service_name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume.json
  tags = local.tags
}

# Attach the AWS managed policy for ECR/Logs
resource "aws_iam_role_policy_attachment" "task_exec_attach" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Optional: user can attach more permissions via inline JSON policy in config later

data "aws_iam_policy_document" "task_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "task" {
  name_prefix = "${local.service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags = local.tags
}

# ---------- Logs ----------
resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${local.service_name}"
  retention_in_days = local.log_retention_days
  tags              = local.tags
}

# ---------- Task Definition ----------
locals {
  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = local.container_image
      essential = true
      cpu       = local.cpu
      memory    = local.memory
      portMappings = local.container_port != null ? [{
        containerPort = local.container_port
        protocol      = "tcp"
      }] : []

      environment = [
        for kv in local.container_env : {
          name  = kv.name
          value = kv.value
        }
      ]

      secrets = [
        for s in local.container_secrets : {
          name      = s.name
          valueFrom = s.valueFrom
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = local.container_name
        }
      }
    }
  ])
}

data "aws_region" "current" {}

resource "aws_ecs_task_definition" "this" {
  family                   = local.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(local.cpu)
  memory                   = tostring(local.memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions    = local.container_definitions
  tags                     = local.tags
}

# ---------- ECS Service ----------
resource "aws_ecs_service" "this" {
  name            = local.service_name
  cluster         = local.cluster_arn
  desired_count   = local.desired_count
  launch_type     = "FARGATE"
  platform_version = local.platform_version

  network_configuration {
    subnets          = local.private_subnet_ids
    security_groups  = local.service_security_groups
    assign_public_ip = local.assign_public_ip
  }

  dynamic "load_balancer" {
    for_each = local.target_group_arn != null && local.container_port != null ? [1] : []
    content {
      target_group_arn = local.target_group_arn
      container_name   = local.container_name
      container_port   = local.container_port
    }
  }

  task_definition = aws_ecs_task_definition.this.arn
  propagate_tags  = "SERVICE"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}

# ---------- Publish service runtime ----------
locals {
  runtime_path = "/iac/ecs-service/${var.nickname}/runtime"
}

resource "aws_ssm_parameter" "runtime" {
  name      = local.runtime_path
  type      = "String"
  overwrite = true
  tier      = "Standard"

  value = jsonencode({
    service_name        = aws_ecs_service.this.name
    service_arn         = aws_ecs_service.this.arn
    task_definition_arn = aws_ecs_task_definition.this.arn
    cluster_arn         = local.cluster_arn
    container_name      = local.container_name
    container_port      = local.container_port
    log_group_name      = aws_cloudwatch_log_group.this.name
    target_group_arn    = local.target_group_arn
    vpc_id              = local.vpc_id
    subnets             = local.private_subnet_ids
    security_groups     = local.service_security_groups
    config_path         = local.config_path
  })

  tags = local.tags
}
