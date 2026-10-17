resource "terraform_data" "mode" {
  input = local.mode
  lifecycle {
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
module "operational" {
  source     = "../../modules/iot-operational"
  count      = local.mode == "operational-telemetry" ? 1 : 0
  config     = local.config
  region     = var.region
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}
resource "aws_ssm_parameter" "runtime" {
  count = local.mode == "operational-telemetry" ? 1 : 0
  name  = "${var.iac_prefix}/${var.component_name}/${var.nickname}/runtime"
  type  = "String"
  value = jsonencode(module.operational[0].runtime)
}
output "runtime" {
  sensitive = true
  value     = jsondecode(local.mode == "operational-telemetry" ? aws_ssm_parameter.runtime[0].value : jsonencode(module.durable[0].runtime))
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
