
locals {
  cluster_name              = try(local.config.cluster_name, "ecs-${var.nickname}")
  enable_execute_command    = try(local.config.enable_execute_command, true)
  exec_logging              = try(local.config.exec_logging, "OVERRIDE") # DEFAULT | OVERRIDE | NONE
  create_log_group          = try(local.config.create_log_group, true)
  log_retention_days        = try(local.config.log_retention_days, 14)
  enable_container_insights = try(local.config.enable_container_insights, false)
  capacity_providers        = try(local.config.capacity_providers, [])
  default_capacity_strategy = try(local.config.default_capacity_strategy, [])

  vpc       = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value))
  vpc_id    = local.vpc.vpc_id
  vpc_sg_id = local.vpc.default_sg_id
  subnet_id = local.vpc.private_subnet_ids[0]
}

data "aws_ssm_parameter" "vpc_runtime" {
  name = "${var.iac_prefix}/vpc/${local.config.vpc_nickname}/runtime"
}

resource "aws_cloudwatch_log_group" "this" {
  count             = local.create_log_group && local.enable_execute_command && local.exec_logging == "OVERRIDE" ? 1 : 0
  name              = "/ecs/${local.cluster_name}/exec"
  retention_in_days = local.log_retention_days
  tags              = local.tags
}

resource "aws_ecs_cluster" "this" {
  name = local.cluster_name
  tags = local.tags

  dynamic "configuration" {
    for_each = local.enable_execute_command ? [1] : []
    content {
      execute_command_configuration {
        logging = local.exec_logging
        dynamic "log_configuration" {
          for_each = local.exec_logging == "OVERRIDE" ? [1] : []
          content {
            cloud_watch_log_group_name = aws_cloudwatch_log_group.this[0].name
          }
        }
      }
    }
  }

  dynamic "setting" {
    for_each = local.enable_container_insights ? [1] : []
    content {
      name  = "containerInsights"
      value = "enabled"
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  count = length(local.capacity_providers) > 0 ? 1 : 0

  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = local.capacity_providers

  dynamic "default_capacity_provider_strategy" {
    for_each = local.default_capacity_strategy
    content {
      capacity_provider = default_capacity_provider_strategy.value.capacity_provider
      weight            = try(default_capacity_provider_strategy.value.weight, null)
      base              = try(default_capacity_provider_strategy.value.base, null)
    }
  }
}

resource "aws_ssm_parameter" "runtime" {
  name      = local.runtime_path
  type      = "String"
  overwrite = true
  tier      = "Standard"

  value = jsonencode({
    # Core identifiers
    cluster_arn  = aws_ecs_cluster.this.arn
    cluster_name = aws_ecs_cluster.this.name

    # Capacity providers / placement defaults
    capacity_providers        = try(aws_ecs_cluster_capacity_providers.this[0].capacity_providers, null)
    default_capacity_strategy = try(local.default_capacity_strategy, null)
  })

  tags = local.tags
}
