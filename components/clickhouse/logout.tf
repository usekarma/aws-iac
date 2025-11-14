#############################################
# Logout Service on ECS (Cognito logout glue)
#############################################

locals {
  # ---------- Service config ----------
  logout_service_name     = try(local.config.logout_service_name, "logout-service")
  logout_desired_count    = try(local.config.logout_desired_count, 1)
  logout_cpu              = try(local.config.logout_cpu, 256)
  logout_memory           = try(local.config.logout_memory, 512)
  logout_platform_version = try(local.config.logout_platform_version, "LATEST")
  logout_assign_public_ip = try(local.config.logout_assign_public_ip, false)

  # Image: override via config.logout_image with full ECR URI
  logout_image = try(local.config.logout_image, "logout-service:latest")

  # Cognito SSO runtime (already decoded into local.cognito_sso in alb.tf)
  # local.cognito_sso = {
  #   user_pool_id     = ...
  #   user_pool_arn    = ...
  #   client_id        = ...
  #   user_pool_domain = ...
  #   region           = ...
  #   hosted_ui_base_url = "https://<domain>.auth.<region>.amazoncognito.com"
  # }

  # Build the full hosted UI host, e.g. "usekarma-obs.auth.us-east-1.amazoncognito.com"
  logout_cognito_domain_host = format(
    "%s.auth.%s.amazoncognito.com",
    local.cognito_sso.user_pool_domain,
    local.cognito_sso.region
  )

  # Where Cognito should send the user after logout (Grafana as canonical landing page)
  logout_redirect_uri = format("https://%s/", local.grafana_host)
}

# ---------- Security Group (logout tasks) ----------
resource "aws_security_group" "logout" {
  name_prefix = "${local.logout_service_name}-sg-"
  description = "SG for logout ECS tasks"
  vpc_id      = local.vpc_id
  tags        = local.tags
}

# Allow inbound from ALB only on 8080
resource "aws_security_group_rule" "logout_from_alb" {
  type                     = "ingress"
  protocol                 = "tcp"
  from_port                = 8080
  to_port                  = 8080
  security_group_id        = aws_security_group.logout.id
  source_security_group_id = aws_security_group.alb.id
}

# Allow all egress
resource "aws_security_group_rule" "logout_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.logout.id
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
}

# ---------- IAM Role for Task ----------
data "aws_iam_policy_document" "logout_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "logout_task" {
  name_prefix        = "${local.logout_service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.logout_task_assume.json
  tags               = local.tags
}

# Attach the standard ECS task execution policy (pull image, write logs, etc.)
resource "aws_iam_role_policy_attachment" "logout_task_exec" {
  role       = aws_iam_role.logout_task.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------- Logs ----------
resource "aws_cloudwatch_log_group" "logout" {
  name              = "/ecs/${local.logout_service_name}"
  retention_in_days = try(local.config.logout_log_retention_days, 14)
  tags              = local.tags
}

# ---------- Target Group (for /logout rule in alb.tf) ----------
resource "aws_lb_target_group" "logout" {
  name_prefix = "lg-"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/healthz"
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  tags = local.tags
}

# ---------- Task Definition ----------
# Uses the logout-image Flask app listening on 8080.
resource "aws_ecs_task_definition" "logout" {
  family                   = local.logout_service_name
  network_mode             = "awsvpc"
  cpu                      = local.logout_cpu
  memory                   = local.logout_memory
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.logout_task.arn
  task_role_arn            = aws_iam_role.logout_task.arn

  container_definitions = jsonencode([
    {
      name      = "logout"
      image     = local.logout_image
      essential = true

      portMappings = [
        {
          containerPort = 8080
          hostPort      = 8080
          protocol      = "tcp"
        }
      ]

      environment = [
        # These line up with the logout-image app expectations
        {
          name  = "COGNITO_CLIENT_ID"
          value = local.cognito_sso.client_id
        },
        {
          name  = "COGNITO_DOMAIN"
          value = local.logout_cognito_domain_host
        },
        {
          name  = "AWS_REGION"
          value = local.cognito_sso.region
        },
        {
          name  = "LOGOUT_REDIRECT_URI"
          value = local.logout_redirect_uri
        },
        # Backwards-compat: some variants of the app use LOGOUT_REDIRECT
        {
          name  = "LOGOUT_REDIRECT"
          value = local.logout_redirect_uri
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://127.0.0.1:8080/healthz || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 5
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.logout.name
          awslogs-region        = data.aws_region.current.id
          awslogs-stream-prefix = "ecs"
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

# ---------- ECS Service ----------
resource "aws_ecs_service" "logout" {
  name             = local.logout_service_name
  cluster          = local.ecs_cluster_arn
  desired_count    = local.logout_desired_count
  launch_type      = "FARGATE"
  platform_version = local.logout_platform_version

  network_configuration {
    subnets         = local.vpc.private_subnet_ids
    security_groups = [aws_security_group.logout.id]
    assign_public_ip = local.logout_assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.logout.arn
    container_name   = "logout"
    container_port   = 8080
  }

  task_definition = aws_ecs_task_definition.logout.arn
  propagate_tags  = "SERVICE"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}
