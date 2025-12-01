#############################################
# Lambda Component – main.tf
#
# Assumptions:
# - header.tf already loads:
#     - var.iac_prefix
#     - var.component_name
#     - var.nickname
#     - local.config  (JSON from /<iac_prefix>/<component_name>/<nickname>/config)
#     - local.tags
#
# - local.config.functions looks like:
#   {
#     "seed-sales-data": {
#       "runtime": "python3.10",
#       "handler": "main.handler",
#       "memory_size": 1024,
#       "timeout": 900,
#       "src_type": "clickhouse",
#       "src_nickname": "usekarma-dev",
#       "vpc_nickname": "usekarma-dev"
#     },
#     ...
#   }
#############################################

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  # All Lambda functions from the JSON config
  functions = try(local.config.functions, {})

  # Subset of functions that declare a VPC nickname
  functions_with_vpc = {
    for name, cfg in local.functions :
    name => cfg
    if try(cfg.vpc_nickname, "") != ""
  }
}

#############################################
# VPC Runtime – SSM (for functions that need VPC config)
#############################################

# Example expected param:
#   /iac/vpc/usekarma-dev/runtime
# with JSON like:
# {
#   "default_sg_id": "sg-059570e5b774cf338",
#   "private_subnet_ids": ["subnet-0690...", "subnet-077d..."],
#   "public_subnet_ids": [...],
#   "vpc_id": "vpc-0a79b1fbd6d28bd1d",
#   ...
# }

data "aws_ssm_parameter" "vpc_runtime" {
  for_each = local.functions_with_vpc

  name = "${var.iac_prefix}/vpc/${each.value.vpc_nickname}/runtime"
}

locals {
  # Raw decoded JSON from the VPC runtime param
  vpc_runtime_decoded_raw = {
    for fname, param in data.aws_ssm_parameter.vpc_runtime :
    fname => jsondecode(param.value)
  }

  # Normalized view with explicit fields we care about.
  # You can later extend the JSON with e.g. "lambda_extra_sg_ids"
  # and they’ll automatically be picked up here.
  vpc_runtime_decoded = {
    for fname, v in local.vpc_runtime_decoded_raw :
    fname => {
      private_subnet_ids = try(v.private_subnet_ids, [])
      default_sg_id      = try(v.default_sg_id, null)
      lambda_extra_sg_ids = try(v.lambda_extra_sg_ids, [])
    }
  }
}

#############################################
# IAM Roles
#############################################

resource "aws_iam_role" "lambda_exec" {
  for_each = local.functions

  name = "lambda-${var.nickname}-${each.key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action   = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

# Basic CloudWatch Logs execution role
resource "aws_iam_role_policy_attachment" "basic_exec" {
  for_each = local.functions

  role       = aws_iam_role.lambda_exec[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Inline policy to allow Lambda to call SSM GetParameter/GetParameters
# so it can resolve src_type/src_nickname/vpc_nickname at runtime.
resource "aws_iam_role_policy" "ssm_access" {
  for_each = local.functions

  role = aws_iam_role.lambda_exec[each.key].name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ],
        # Example ARN:
        # arn:aws:ssm:us-east-1:123456789012:parameter/iac/*
        Resource = "arn:aws:ssm:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:parameter${var.iac_prefix}/*"
      }
    ]
  })
}

# Inline policy for ENI / VPC access (instead of attaching AWSLambdaVPCAccessExecutionRole).
resource "aws_iam_role_policy" "vpc_access" {
  for_each = local.functions_with_vpc

  role = aws_iam_role.lambda_exec[each.key].name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ],
        Resource = "*"
      }
    ]
  })
}

#############################################
# Lambda Functions (placeholders)
#############################################

resource "aws_lambda_function" "placeholder" {
  for_each = local.functions

  function_name = each.key
  role          = aws_iam_role.lambda_exec[each.key].arn
  handler       = each.value.handler
  runtime       = each.value.runtime
  memory_size   = each.value.memory_size
  timeout       = each.value.timeout

  # Tiny placeholder zip; real code is deployed via deploy_lambda.py
  filename         = "${path.module}/empty.zip"
  source_code_hash = filebase64sha256("${path.module}/empty.zip")

  # Generic discovery env vars so the Lambda can:
  # - resolve its source runtime (/iac/<SRC_TYPE>/<SRC_NICKNAME>/runtime)
  # - know which VPC runtime to read (/iac/vpc/<VPC_NICKNAME>/runtime)
  # - know the iac prefix and component at runtime if needed.
  environment {
    variables = {
      SRC_TYPE       = try(each.value.src_type, "")
      SRC_NICKNAME   = try(each.value.src_nickname, "")
      VPC_NICKNAME   = try(each.value.vpc_nickname, "")
      IAC_PREFIX     = var.iac_prefix
      COMPONENT_NAME = var.component_name
    }
  }

  # Only functions with a vpc_nickname get a vpc_config block.
  dynamic "vpc_config" {
    for_each = contains(keys(local.vpc_runtime_decoded), each.key) ? [1] : []

    content {
      subnet_ids = local.vpc_runtime_decoded[each.key].private_subnet_ids

      # 👇 Always include the default VPC SG, plus any optional lambda_extra_sg_ids
      security_group_ids = compact(
        concat(
          [local.vpc_runtime_decoded[each.key].default_sg_id],
          local.vpc_runtime_decoded[each.key].lambda_extra_sg_ids
        )
      )
    }
  }

  lifecycle {
    # Code is managed out-of-band by deploy_lambda.py
    ignore_changes = [filename, source_code_hash]
  }

  tags = local.tags
}

#############################################
# NOTE: No aws_ssm_parameter "runtime" here.
# Runtime ARNs (/iac/lambda/<fn>/runtime) are owned by deploy_lambda.py
# or whatever deployment pipeline you're using.
#############################################
