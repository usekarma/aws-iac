locals {
  # ---------- Service config ----------
  redpanda_console_service_name     = try(local.config.redpanda_console_service_name, "redpanda-console")
  redpanda_console_desired_count    = try(local.config.redpanda_console_desired_count, 1)
  redpanda_console_cpu              = try(local.config.redpanda_console_cpu, 256)
  redpanda_console_memory           = try(local.config.redpanda_console_memory, 512)
  redpanda_console_platform_version = try(local.config.redpanda_console_platform_version, "LATEST")
  redpanda_console_assign_public_ip = try(local.config.redpanda_console_assign_public_ip, false)

  # Official image
  redpanda_console_image = try(local.config.redpanda_console_image, "docker.redpanda.com/redpandadata/console:latest")

  # Logs
  redpanda_console_log_retention_days = try(local.config.redpanda_console_log_retention_days, 14)
}

resource "aws_security_group" "redpanda_console" {
  count       = local.enable_redpanda ? 1 : 0
  name_prefix = "${local.redpanda_console_service_name}-sg-"
  description = "SG for Redpanda Console ECS tasks"
  vpc_id      = local.vpc_id
  tags        = local.tags
}

resource "aws_security_group_rule" "redpanda_console_from_alb" {
  count                   = local.enable_redpanda ? 1 : 0
  type                    = "ingress"
  protocol                = "tcp"
  from_port               = 8080
  to_port                 = 8080
  security_group_id       = aws_security_group.redpanda_console[0].id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "redpanda_console_egress_all" {
  count            = local.enable_redpanda ? 1 : 0
  type             = "egress"
  from_port        = 0
  to_port          = 0
  protocol         = "-1"
  security_group_id = aws_security_group.redpanda_console[0].id
  cidr_blocks      = ["0.0.0.0/0"]
  ipv6_cidr_blocks = ["::/0"]
}

data "aws_iam_policy_document" "redpanda_console_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "redpanda_console_task" {
  count              = local.enable_redpanda ? 1 : 0
  name_prefix        = "${local.redpanda_console_service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.redpanda_console_task_assume.json
  tags               = local.tags
}

# Attach the standard ECS task execution policy (pull image, write logs, etc.)
resource "aws_iam_role_policy_attachment" "redpanda_console_task_exec" {
  count      = local.enable_redpanda ? 1 : 0
  role       = aws_iam_role.redpanda_console_task[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_cloudwatch_log_group" "redpanda_console" {
  count             = local.enable_redpanda ? 1 : 0
  name              = "/ecs/${local.redpanda_console_service_name}"
  retention_in_days = local.redpanda_console_log_retention_days
  tags              = local.tags
}

resource "aws_lb_target_group" "redpanda_console" {
  count      = local.enable_redpanda ? 1 : 0
  name_prefix = "rpc-"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = local.vpc_id
  target_type = "ip"

  health_check {
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }

  tags = local.tags
}

resource "aws_ecs_task_definition" "redpanda_console" {
  count                    = local.enable_redpanda ? 1 : 0
  family                   = local.redpanda_console_service_name
  network_mode             = "awsvpc"
  cpu                      = local.redpanda_console_cpu
  memory                   = local.redpanda_console_memory
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.redpanda_console_task[0].arn
  task_role_arn            = aws_iam_role.redpanda_console_task[0].arn

  container_definitions = jsonencode([
    {
      "name": "redpanda-console",
      "image": local.redpanda_console_image,
      "essential": true,
      "portMappings": [
        { "containerPort": 8080, "hostPort": 8080, "protocol": "tcp" }
      ],
      "environment": [
        # -------- Core: broker connectivity --------
        { "name": "KAFKA_BROKERS", "value": local.redpanda_brokers },

        # -------- Disable ALL Console-side auth (no login screen) --------
        { "name": "AUTHENTICATION_BASIC_ENABLED", "value": "false" },
        { "name": "AUTHENTICATION_OIDC_ENABLED",  "value": "false" },

        # -------- Connect UI (optional, keep if you want it) --------
        { "name": "CONNECT_ENABLED",            "value": "true" },
        { "name": "CONNECT_CLUSTERS_0_NAME",    "value": "connect-cluster" },
        { "name": "CONNECT_CLUSTERS_0_URL",     "value": local.kconnect_url },

        # Optional: schema registry
        { "name": "SCHEMAREGISTRY_ENABLED", "value": "false" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": aws_cloudwatch_log_group.redpanda_console[0].name,
          "awslogs-region": data.aws_region.current.id,
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = local.tags
}

resource "aws_ecs_service" "redpanda_console" {
  count            = local.enable_redpanda ? 1 : 0
  name             = local.redpanda_console_service_name
  cluster          = local.ecs_cluster_arn
  desired_count    = local.redpanda_console_desired_count
  launch_type      = "FARGATE"
  platform_version = local.redpanda_console_platform_version

  network_configuration {
    subnets         = local.vpc.private_subnet_ids
    security_groups = [aws_security_group.redpanda_console[0].id, local.vpc_sg_id]
    assign_public_ip = local.redpanda_console_assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.redpanda_console[0].arn
    container_name   = "redpanda-console"
    container_port   = 8080
  }

  task_definition = aws_ecs_task_definition.redpanda_console[0].arn
  propagate_tags  = "SERVICE"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}
