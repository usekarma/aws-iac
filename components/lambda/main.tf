# Lambda declarations come from aws-config; IAM and deployment stay in aws-iac.
# Every function requires a versioned artifact; no external code/runtime owner.

data "aws_caller_identity" "current" {}

locals {
  # All Lambda functions from the JSON config
  functions = local.config.functions

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
  vpc_runtime_decoded = {
    for fname, param in data.aws_ssm_parameter.vpc_runtime :
    fname => jsondecode(param.value)
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
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
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
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.iac_prefix}/*"
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

module "functions" {
  source    = "../../modules/lambda"
  functions = local.functions
  bindings = {
    for name, cfg in local.functions : name => {
      function_name = name
      role_arn      = aws_iam_role.lambda_exec[name].arn
      environment = {
        SRC_TYPE       = try(cfg.src_type, "")
        SRC_NICKNAME   = try(cfg.src_nickname, "")
        VPC_NICKNAME   = try(cfg.vpc_nickname, "")
        IAC_PREFIX     = var.iac_prefix
        COMPONENT_NAME = var.component_name
      }
      vpc = contains(keys(local.vpc_runtime_decoded), name) ? {
        subnet_ids         = local.vpc_runtime_decoded[name].private_subnet_ids
        security_group_ids = [local.vpc_runtime_decoded[name].default_sg_id]
      } : null
    }
  }
  tags = local.tags
  depends_on = [
    aws_iam_role_policy_attachment.basic_exec,
    aws_iam_role_policy.ssm_access,
    aws_iam_role_policy.vpc_access,
  ]
}

moved {
  from = aws_lambda_function.placeholder
  to   = module.functions.aws_lambda_function.this
}

resource "aws_ssm_parameter" "runtime" {
  for_each = local.functions
  name     = "${var.iac_prefix}/${var.component_name}/${each.key}/runtime"
  type     = "String"
  value = jsonencode({
    function_name = module.functions.functions[each.key].function_name
    arn           = module.functions.functions[each.key].arn
    invoke_arn    = module.functions.functions[each.key].invoke_arn
    artifact      = each.value.artifact
    runtime       = each.value.runtime
    handler       = each.value.handler
  })
  overwrite = true
  tier      = "Standard"
}
