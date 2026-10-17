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
  name        = "iot_digital_twin_simulator_reset"
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
