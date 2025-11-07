locals {
  ecs_cluster_nickname = try(local.config.ecs_cluster_nickname, null)
  ecs_cluster          = try(jsondecode(data.aws_ssm_parameter.ecs_cluster_runtime.value), {})
  ecs_cluster_arn      = try(local.ecs_cluster.cluster_arn, null)

  enable_kconnect = try(local.config.enable_kconnect, true)

  kconnect_service_name     = try(local.config.kconnect_service_name, "svc-${var.nickname}")
  kconnect_desired_count    = try(local.config.kconnect_desired_count, 1)
  kconnect_cpu              = try(local.config.kconnect_cpu, 1024)
  kconnect_memory           = try(local.config.kconnect_memory, 2048)
  kconnect_platform_version = try(local.config.kconnect_platform_version, "LATEST")
  kconnect_assign_public_ip = try(local.config.kconnect_assign_public_ip, false)

  kconnect       = try(local.config.kconnect, {})
  kconnect_name  = try(local.kconnect.name, "kconnect")
  kconnect_image = try(local.kconnect.image, "quay.io/debezium/connect:3.3.1.Final")
  kconnect_port  = try(local.kconnect.port, 8083)

  kconnect_rest_host = data.external.kconnect_private_ip.result.private_ip

  # Construct default ECR fallback URI dynamically
  kconnect_metrics_repo           = "clickhouse-kconnect-jmx-exporter"
  kconnect_metrics_fallback_image = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.id}.amazonaws.com/${local.kconnect_metrics_repo}:latest"

  # metrics sidecar image (ECR URI) – optional override from config.json
  kconnect_metrics_image = coalesce(try(local.config.kconnect_metrics_image, null), local.kconnect_metrics_fallback_image)

  kconnect_log_retention_days = try(local.kconnect.log_retention_days, 14)
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

data "external" "kconnect_private_ip" {
  program = [
    "bash", "-c",
    <<-EOT
      ip=$(aws ecs list-tasks --cluster ${local.ecs_cluster_arn} \
            --service-name ${aws_ecs_service.kconnect.name} \
            --query 'taskArns[0]' --output text |
            xargs -I {} aws ecs describe-tasks \
              --cluster ${local.ecs_cluster_arn} \
              --tasks {} \
              --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' \
              --output text)
      echo "{\"private_ip\": \"$ip\"}"
    EOT
  ]
}

resource "aws_iam_role" "task_execution" {
  name_prefix        = "${local.kconnect_service_name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "task_exec_attach" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

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
  cpu                      = tostring(local.kconnect_cpu)    # 1024
  memory                   = tostring(local.kconnect_memory) # 2048
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "kconnect"
      image     = local.kconnect_image
      essential = true

      portMappings = [
        {
          containerPort = local.kconnect_port # 8083
          protocol      = "tcp"
        },
        {
          containerPort = 9010 # JMX
          protocol      = "tcp"
        }
      ]

      environment = [
        # Kafka bootstrap (Redpanda)
        {
          name  = "BOOTSTRAP_SERVERS"
          value = "${aws_instance.redpanda[0].private_ip}:${local.redpanda_port}"
        },

        # Mongo replica set URI (for Debezium)
        {
          name  = "MONGODB_CONNECTION_STRING"
          value = local.mongo_connection_string
        },

        # Kafka Connect internal topics / config
        {
          name  = "GROUP_ID"
          value = try(local.config.kconnect_group_id, "clickhouse-connect")
        },
        {
          name  = "CONFIG_STORAGE_TOPIC"
          value = try(local.config.kconnect_config_topic, "kconnect-config")
        },
        {
          name  = "OFFSET_STORAGE_TOPIC"
          value = try(local.config.kconnect_offset_topic, "kconnect-offsets")
        },
        {
          name  = "STATUS_STORAGE_TOPIC"
          value = try(local.config.kconnect_status_topic, "kconnect-status")
        },

        # JSON converters (no schemas)
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
        },
        {
          name  = "REST_PORT"
          value = tostring(local.kconnect_port)
        },


        # --- Enable JMX for Kafka Connect ---
        {
          name = "KAFKA_JMX_OPTS"
          value = join(" ", [
            "-Dcom.sun.management.jmxremote",
            "-Dcom.sun.management.jmxremote.local.only=false",
            "-Dcom.sun.management.jmxremote.authenticate=false",
            "-Dcom.sun.management.jmxremote.ssl=false",
            "-Dcom.sun.management.jmxremote.port=9010",
            "-Djava.rmi.server.hostname=0.0.0.0"
          ])
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.kconnect.name
          awslogs-region        = data.aws_region.current.id
          awslogs-stream-prefix = "ecs"
        }
      }
    },
    {
      name      = "kconnect-metrics"
      image     = coalesce(local.kconnect_metrics_image, "usekarma/kconnect-jmx-exporter:latest")
      essential = false

      portMappings = [
        {
          containerPort = 9404 # Prometheus will scrape here
          protocol      = "tcp"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.kconnect.name
          awslogs-region        = data.aws_region.current.id
          awslogs-stream-prefix = "ecs-metrics"
        }
      }
    }
  ])

  tags = local.tags
}

resource "null_resource" "mongo_cdc_connector_apply" {
  # Wait for these to exist before trying to hit Connect
  depends_on = [
    aws_ecs_service.kconnect, # your Fargate Connect service
    aws_instance.mongo,       # Mongo EC2
    local_file.mongo_cdc_connector
  ]

  # Re-run whenever config or target host changes
  triggers = {
    connector_hash = sha1(local.mongo_cdc_connector_json)
    rest_host      = local.kconnect_rest_host
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      echo "Applying Debezium Mongo connector: mongo-cdc-sales-orders to ${local.kconnect_rest_host}..."

      # Use PUT so it's idempotent: create or update connector config in one shot
      curl -sS -X PUT "http://${local.kconnect_rest_host}:8083/connectors/mongo-cdc-sales-orders/config" \
        -H "Content-Type: application/json" \
        --data-binary "@${local_file.mongo_cdc_connector.filename}"

      echo
      echo "Checking connector status..."
      curl -sS "http://${local.kconnect_rest_host}:8083/connectors/mongo-cdc-sales-orders/status" || true
      echo
    EOT
  }
}
