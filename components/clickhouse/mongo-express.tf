locals {
  # Basic ECS service settings for mongo-express
  mongo_express_service_name     = try(local.config.mongo_express_service_name, "mongo-express")
  mongo_express_desired_count    = try(local.config.mongo_express_desired_count, 1)
  mongo_express_cpu              = try(local.config.mongo_express_cpu, 256)
  mongo_express_memory           = try(local.config.mongo_express_memory, 512)
  mongo_express_platform_version = try(local.config.mongo_express_platform_version, "LATEST")
  mongo_express_assign_public_ip = try(local.config.mongo_express_assign_public_ip, false)

  mongo_express_image = try(local.config.mongo_express_image, "mongo-express:latest")

  mongo_express_log_retention_days = try(local.config.mongo_express_log_retention_days, 14)
}

# ---------- Security Group for mongo-express ECS tasks ----------
resource "aws_security_group" "mongo_express" {
  count       = local.enable_mongo ? 1 : 0
  name_prefix = "${local.mongo_express_service_name}-sg-"
  description = "Security group for ${local.mongo_express_service_name} ECS service"
  vpc_id      = local.vpc.vpc_id

  # Outbound: allow everything (typical for ECS tasks)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# Allow ALB -> mongo-express on 8081
resource "aws_security_group_rule" "mongo_express_from_alb" {
  count = local.enable_mongo ? 1 : 0

  type                     = "ingress"
  description              = "Allow ALB to reach mongo-express on 8081"
  from_port                = 8081
  to_port                  = 8081
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mongo_express[0].id
  source_security_group_id = aws_security_group.alb.id
}

# Allow mongo-express tasks -> MongoDB on mongo port
resource "aws_security_group_rule" "mongo_from_mongo_express" {
  count = local.enable_mongo ? 1 : 0

  type                     = "ingress"
  description              = "Allow mongo-express ECS tasks to talk to MongoDB on ${local.mongo_port}"
  from_port                = local.mongo_port
  to_port                  = local.mongo_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mongo[0].id
  source_security_group_id = aws_security_group.mongo_express[0].id
}

# ---------- IAM roles for task ----------
data "aws_iam_policy_document" "mongo_express_task_execution_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "mongo_express_task_execution" {
  count              = local.enable_mongo ? 1 : 0
  name_prefix        = "${local.mongo_express_service_name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.mongo_express_task_execution_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "mongo_express_task_exec_attach" {
  count      = local.enable_mongo ? 1 : 0
  role       = aws_iam_role.mongo_express_task_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "mongo_express_task_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "mongo_express_task" {
  count              = local.enable_mongo ? 1 : 0
  name_prefix        = "${local.mongo_express_service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.mongo_express_task_assume.json
  tags               = local.tags
}

# ---------- Logs ----------
resource "aws_cloudwatch_log_group" "mongo_express" {
  count             = local.enable_mongo ? 1 : 0
  name              = "/ecs/${local.mongo_express_service_name}"
  retention_in_days = local.mongo_express_log_retention_days
  tags              = local.tags
}

# ---------- ECS Task Definition ----------
resource "aws_ecs_task_definition" "mongo_express" {
  count                    = local.enable_mongo ? 1 : 0
  family                   = local.mongo_express_service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(local.mongo_express_cpu)
  memory                   = tostring(local.mongo_express_memory)
  execution_role_arn       = aws_iam_role.mongo_express_task_execution[0].arn
  task_role_arn            = aws_iam_role.mongo_express_task[0].arn

  container_definitions = jsonencode([
    {
      name      = "mongo-express"
      image     = local.mongo_express_image
      essential = true

      portMappings = [
        {
          containerPort = 8081
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ME_CONFIG_MONGODB_URL"
          value = local.mongo_connection_string
        },
        {
          name  = "ME_CONFIG_MONGODB_ENABLE_ADMIN"
          value = "true"
        },
        {
          name  = "ME_CONFIG_BASICAUTH"
          value = "false"
        }

      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.mongo_express[0].name
          awslogs-region        = data.aws_region.current.id
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = local.tags
}

# ---------- ECS Service ----------
resource "aws_ecs_service" "mongo_express" {
  count            = local.enable_mongo ? 1 : 0
  name             = local.mongo_express_service_name
  cluster          = local.ecs_cluster_arn
  desired_count    = local.mongo_express_desired_count
  launch_type      = "FARGATE"
  platform_version = local.mongo_express_platform_version

  network_configuration {
    subnets          = local.vpc.private_subnet_ids
    security_groups  = [local.vpc.default_sg_id, aws_security_group.mongo_express[0].id]
    assign_public_ip = local.mongo_express_assign_public_ip
  }

  # Wire ECS -> ALB target group
  load_balancer {
    target_group_arn = aws_lb_target_group.mongo_express[0].arn
    container_name   = "mongo-express"
    container_port   = 8081
  }

  task_definition = aws_ecs_task_definition.mongo_express[0].arn
  propagate_tags  = "SERVICE"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.tags
}
