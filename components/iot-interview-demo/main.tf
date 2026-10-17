terraform {
  backend "s3" {}
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.69.1" }
  }
}
variable "region" { type = string }
variable "component_name" { type = string }
variable "nickname" { type = string }
variable "iac_prefix" {
  type    = string
  default = "/iac"
}
provider "aws" { region = var.region }
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_ssm_parameter" "config" {
  name = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
}
locals {
  config        = nonsensitive(jsondecode(data.aws_ssm_parameter.config.value))
  artifact      = local.config.artifact
  table_name    = "iot-interview-demo-state"
  request_topic = "devices/atom-lite-001/demo/reset/request"
  ack_topic     = "devices/atom-lite-001/demo/reset/ack"
  functions = {
    runner = { name = "iot-interview-demo-runner", handler = "app.runner_handler", timeout = 210 }
    reset  = { name = "iot-interview-demo-reset", handler = "app.reset_handler", timeout = 10 }
  }
  tags = { Project = "iot-interview-demo", Environment = "sandbox" }
}
resource "aws_dynamodb_table" "state" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  tags = local.tags
}
resource "aws_iam_role" "runtime" {
  for_each = local.functions
  name     = "${each.value.name}-role"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
  tags = local.tags
}
resource "aws_cloudwatch_log_group" "runtime" {
  for_each          = local.functions
  name              = "/aws/lambda/${each.value.name}"
  retention_in_days = 7
  tags              = local.tags
}
resource "aws_iam_role_policy" "runtime" {
  for_each = local.functions
  role     = aws_iam_role.runtime[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect   = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
      Resource = aws_dynamodb_table.state.arn,
    Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["SESSION#${local.config.active_session}"] } } },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = "${aws_cloudwatch_log_group.runtime[each.key].arn}:*" }
    ], each.key == "reset" ? [
    { Effect = "Allow", Action = ["iot:Publish"],
    Resource = "arn:${data.aws_partition.current.partition}:iot:${var.region}:${data.aws_caller_identity.current.account_id}:topic/${local.ack_topic}" }
  ] : []) })
}
resource "aws_lambda_function" "runtime" {
  for_each                       = local.functions
  function_name                  = each.value.name
  handler                        = each.value.handler
  runtime                        = "python3.12"
  memory_size                    = 256
  timeout                        = each.value.timeout
  reserved_concurrent_executions = each.key == "runner" ? 1 : 2
  role                           = aws_iam_role.runtime[each.key].arn
  s3_bucket                      = local.artifact.s3_bucket
  s3_key                         = local.artifact.s3_key
  s3_object_version              = local.artifact.s3_object_version
  source_code_hash               = local.artifact.source_code_hash
  environment {
    variables = {
      STATE_TABLE        = aws_dynamodb_table.state.name
      MODEL_COMMIT       = local.config.model_commit
      ACTIVE_SESSION     = local.config.active_session
      EXPECTED_PRINCIPAL = local.config.expected_principal
      REQUEST_TOPIC      = local.request_topic
      ACK_TOPIC          = local.ack_topic
    }
  }
  lifecycle {
    precondition {
      condition     = can(regex("^[0-9a-f]{40}$", local.config.model_commit)) && can(regex("^[0-9a-f]{32}$", local.config.active_session)) && length(trimspace(local.config.expected_principal)) > 0 && !contains(["", "null", "latest"], local.artifact.s3_object_version) && can(regex("^[A-Za-z0-9+/]{43}=$", local.artifact.source_code_hash))
      error_message = "Resolve exact model/session/principal and immutable artifact version/hash before planning."
    }
  }
  tags       = local.tags
  depends_on = [aws_cloudwatch_log_group.runtime, aws_iam_role_policy.runtime]
}
resource "aws_iot_topic_rule" "reset" {
  name        = "iot_interview_demo_reset"
  enabled     = true
  sql_version = "2016-03-23"
  sql         = "SELECT session_id, command_id, expected_epoch, principal() AS principal, topic() AS topic FROM '${local.request_topic}'"
  lambda { function_arn = aws_lambda_function.runtime["reset"].arn }
}
resource "aws_lambda_permission" "reset_rule" {
  statement_id   = "ExactIoTResetRule"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.runtime["reset"].function_name
  principal      = "iot.amazonaws.com"
  source_arn     = aws_iot_topic_rule.reset.arn
  source_account = data.aws_caller_identity.current.account_id
}
output "runtime" {
  value = { table = aws_dynamodb_table.state.name, functions = { for k, f in aws_lambda_function.runtime : k => f.arn } }
}
