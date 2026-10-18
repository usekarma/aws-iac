resource "terraform_data" "mode" {
  input = local.mode
  lifecycle {
    precondition {
      condition     = !can(local.config.deployment_stage) || (local.mode == "operational-telemetry" && contains(["service-role-bootstrap", "operational"], local.deployment_stage))
      error_message = "Explicit deployment stage must be a supported operational stage."
    }

    precondition {
      condition     = !local.managed_cloud_control || (var.component_name == "iot-digital-twin" && var.nickname == "operational-demo" && var.region == "us-east-1" && try(local.config.region, "") == "us-east-1" && try(local.config.expected_account, "") == "623155450153" && data.aws_caller_identity.current.account_id == "623155450153")
      error_message = "Managed M1 bootstrap uses only the canonical operational-demo owner in 623155450153/us-east-1."
    }
    precondition {
      condition     = !local.bootstrap || (try(local.config.cloudformation_role_arn, null) == null && !try(local.config.awscc_request_tags_verified, false) && can(regex("^[0-9a-f]{64}$", local.config.expected_principal)) && !can(local.config.planning_dependencies))
      error_message = "Bootstrap must not bind an uncreated role or assert handler validation."
    }
    precondition {
      condition     = !local.managed_cloud_control || local.bootstrap || (try(local.config.cloudformation_role_arn, "") == try(data.aws_iam_role.verified_cloud_control[0].arn, null) && try(local.config.awscc_request_tags_verified, false))
      error_message = "Stage 2 needs the verified same-owner role ARN and explicit request-tag evidence."
    }
    precondition {
      condition     = contains(["durable-simulator", "operational-telemetry"], local.mode)
      error_message = "Unsupported IoT Digital Twin mode."
    }
  }
}
module "durable" {
  source = "../../modules/iot-simulator"
  count  = local.mode == "durable-simulator" ? 1 : 0
  config = local.config
  region = var.region
}
module "cloud_control" {
  source = "../../modules/iot-operational-service-role"
  count  = local.managed_cloud_control ? 1 : 0
}
module "operational" {
  source     = "../../modules/iot-operational"
  count      = local.mode == "operational-telemetry" && !local.bootstrap ? 1 : 0
  config     = local.config
  region     = var.region
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}
resource "aws_ssm_parameter" "runtime" {
  count = local.mode == "operational-telemetry" && !local.bootstrap ? 1 : 0
  name  = "${var.iac_prefix}/${var.component_name}/${var.nickname}/runtime"
  type  = "String"
  value = jsonencode(module.operational[0].runtime)
}
output "runtime" {
  sensitive = true
  value     = jsondecode(local.bootstrap ? jsonencode({ stage = "service-role-bootstrap", service_role_arn = module.cloud_control[0].service_role_arn }) : local.mode == "operational-telemetry" ? aws_ssm_parameter.runtime[0].value : jsonencode(module.durable[0].runtime))
}

moved {
  from = aws_dynamodb_table.state
  to   = module.durable[0].aws_dynamodb_table.state
}

moved {
  from = aws_iam_role.runtime
  to   = module.durable[0].aws_iam_role.runtime
}

moved {
  from = aws_cloudwatch_log_group.runtime
  to   = module.durable[0].aws_cloudwatch_log_group.runtime
}

moved {
  from = aws_iam_role_policy.runtime
  to   = module.durable[0].aws_iam_role_policy.runtime
}

moved {
  from = aws_lambda_function.runtime
  to   = module.durable[0].aws_lambda_function.runtime
}

moved {
  from = aws_iot_topic_rule.reset
  to   = module.durable[0].aws_iot_topic_rule.reset
}

moved {
  from = aws_lambda_permission.reset_rule
  to   = module.durable[0].aws_lambda_permission.reset_rule
}
