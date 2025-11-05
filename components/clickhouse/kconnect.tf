locals {
  ecs_cluster_nickname = try(local.cfg.ecs_cluster_nickname, null)
  ecs_cluster          = try(jsondecode(data.aws_ssm_parameter.ecs_cluster_runtime.value), {})
  ecs_cluster_arn      = try(local.ecs_cluster.cluster_arn, null)

  enable_kconnect = try(local.cfg.enable_kconnect, true)

  kconnect_service_name     = try(local.cfg.kconnect_service_name, "svc-${var.nickname}")
  kconnect_desired_count    = try(local.cfg.kconnect_desired_count, 1)
  kconnect_cpu              = try(local.cfg.kconnect_cpu, 256)
  kconnect_memory           = try(local.cfg.mkconnect_emory, 512)
  kconnect_platform_version = try(local.cfg.kconnect_platform_version, "LATEST")
  kconnect_assign_public_ip = try(local.cfg.kconnect_assign_public_ip, false)

  kconnect       = try(local.cfg.kconnect, {})
  kconnect_name  = try(local.kconnect.name, "kconnect")
  kconnect_image = try(local.kconnect.image, null)
  kconnect_port  = try(local.kconnect.port, null)

  kconnect_log_retention_days = try(local.kconnect.log_retention_days.port, 14)
}

data "aws_ssm_parameter" "ecs_cluster_runtime" {
  name = "${var.iac_prefix}/ecs-cluster/${local.config.ecs_cluster_nickname}/runtime"
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
  name_prefix        = "${local.kconnect_service_name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume.json
  tags               = local.tags
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
  name_prefix        = "${local.kconnect_service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.tags
}

# ---------- Logs ----------
resource "aws_cloudwatch_log_group" "kconnect" {
  name              = "/ecs/${local.kconnect_service_name}"
  retention_in_days = local.kconnect_log_retention_days
  tags              = local.tags
}

data "aws_region" "current" {}

# ---------- ECS Service ----------
resource "aws_ecs_service" "kconnect" {
  name             = local.kconnect_service_name
  cluster          = local.ecs_cluster_arn
  desired_count    = local.kconnect_desired_count
  launch_type      = "FARGATE"
  platform_version = local.kconnect_platform_version

  network_configuration {
    subnets          = local.vpc.private_subnet_ids
    security_groups  = [local.vpc.default_sg_id]
    assign_public_ip = local.kconnect_assign_public_ip
  }

  task_definition = aws_ecs_task_definition.kconnect.arn
  propagate_tags  = "SERVICE"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}

resource "aws_ecs_task_definition" "kconnect" {
  family                   = local.kconnect_service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(local.kconnect_cpu)
  memory                   = tostring(local.kconnect_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "kconnect"
      image     = try(local.cfg.kconnect_image, "debezium/connect:2.7")
      essential = true

      portMappings = [
        {
          containerPort = try(local.cfg.kconnect_port, 8083)
          protocol      = "tcp"
        }
      ]

      # --- Key part: derive env vars from existing resources/locals ---
      environment = [
        # Kafka bootstrap (Redpanda)
        {
          name  = "BOOTSTRAP_SERVERS"
          value = "${aws_instance.redpanda[0].private_ip}:${local.redpanda_port}"
        },

        # Mongo replica set URI (for Debezium)
        {
          name  = "MONGODB_CONNECTION_STRING"
          value = "mongodb://${aws_instance.mongo[0].private_ip}:${local.mongo_port}/?replicaSet=rs0"
        },

        # Kafka Connect internal topics / config
        {
          name  = "GROUP_ID"
          value = try(local.cfg.kconnect_group_id, "clickhouse-connect")
        },
        {
          name  = "CONFIG_STORAGE_TOPIC"
          value = try(local.cfg.kconnect_config_topic, "kconnect-config")
        },
        {
          name  = "OFFSET_STORAGE_TOPIC"
          value = try(local.cfg.kconnect_offset_topic, "kconnect-offsets")
        },
        {
          name  = "STATUS_STORAGE_TOPIC"
          value = try(local.cfg.kconnect_status_topic, "kconnect-status")
        },

        # JSON converters (no schemas) – easy for ClickHouse ingestion
        {
          name  = "KEY_CONVERTER"
          value = "org.apache.kafka.connect.json.JsonConverter"
        },
        {
          name  = "VALUE_CONVERTER"
          value = "org.apache.kafka.connect.json.JsonConverter"
        },
        {
          name  = "KEY_CONVERTER_SCHEMAS_ENABLE"
          value = "false"
        },
        {
          name  = "VALUE_CONVERTER_SCHEMAS_ENABLE"
          value = "false"
        },
        {
          name  = "ENABLE_DEBEZIUM_SCRIPTING"
          value = "true"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.kconnect.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = local.tags
}
