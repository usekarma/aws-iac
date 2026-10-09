data "aws_caller_identity" "current" {}

locals {
  server_derived_connectivity = try(local.config.connectivity_state_server_derived, true)
  reject_device_offline       = try(local.config.reject_device_authored_offline, true)
  device_cert_authoritative   = try(local.config.device_certificate_authoritative, true)
  server_replay_stale         = try(local.config.server_replay_and_stale_enforcement, true)
  device_id_is_data_only      = try(local.config.device_id_is_data_only, true)
  cloudwatch_retention        = try(local.config.cloudwatch_log_retention_days, 30)
}

resource "aws_iot_thing" "device" {
  name = local.thing_name

  attributes = {
    project                        = local.project
    device_id                      = local.device_id
    mqtt_topic                     = local.mqtt_topic
    server_derived_connectivity    = tostring(local.server_derived_connectivity)
    device_id_is_data_only         = tostring(local.device_id_is_data_only)
    reject_device_authored_offline = tostring(local.reject_device_offline)
  }
}

resource "aws_iot_policy" "device" {
  name = "${local.thing_name}-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ConnectToThing"
        Effect   = "Allow"
        Action   = "iot:Connect"
        Resource = "arn:aws:iot:${var.region}:${data.aws_caller_identity.current.account_id}:client/${local.thing_name}"
      },
      {
        Sid      = "PublishTelemetry"
        Effect   = "Allow"
        Action   = "iot:Publish"
        Resource = "arn:aws:iot:${var.region}:${data.aws_caller_identity.current.account_id}:topic/${local.mqtt_topic}"
      },
      {
        Sid      = "ReceiveTelemetry"
        Effect   = "Allow"
        Action   = "iot:Receive"
        Resource = "arn:aws:iot:${var.region}:${data.aws_caller_identity.current.account_id}:topicfilter/${local.mqtt_topic}"
      }
    ]
  })
}

resource "aws_iam_role" "ingest_lambda" {
  name = local.lambda_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ingest_lambda_basic" {
  role       = aws_iam_role.ingest_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ingest_lambda_runtime" {
  name = "${local.lambda_name}-runtime"
  role = aws_iam_role.ingest_lambda.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.latest_state.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.iac_prefix}/*"
      }
    ]
  })
}

resource "aws_lambda_function" "ingest" {
  function_name = local.lambda_name
  role          = aws_iam_role.ingest_lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 512
  timeout       = 30

  filename         = "${path.module}/empty.zip"
  source_code_hash = filebase64sha256("${path.module}/empty.zip")

  environment {
    variables = {
      DEVICE_ID      = local.device_id
      THING_NAME     = local.thing_name
      MQTT_TOPIC     = local.mqtt_topic
      IAC_PREFIX     = var.iac_prefix
      STATE_TABLE    = aws_dynamodb_table.latest_state.name
      PROJECT_NAME   = local.project
      SERVER_REPLAY  = tostring(local.server_replay_stale)
      CONNECTIVITY   = tostring(local.server_derived_connectivity)
      TWIN_WORKSPACE = local.twin_workspace
      TWIN_ENTITY    = local.twin_entity
      TWIN_COMPONENT = local.twin_component
      TWIN_TYPE      = local.twin_type
    }
  }

  tags = local.tags
}

resource "aws_lambda_permission" "iot_trigger" {
  statement_id  = "AllowExecutionFromIoTTopicRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "iot.amazonaws.com"
  source_arn    = aws_iot_topic_rule.telemetry.arn
}

resource "aws_iot_topic_rule" "telemetry" {
  name        = local.iot_rule_name
  enabled     = true
  sql         = "SELECT * FROM '${local.mqtt_topic}'"
  sql_version = "2016-03-23"

  lambda {
    function_arn = aws_lambda_function.ingest.arn
  }
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = local.cloudwatch_retention
  tags              = local.tags
}

resource "aws_dynamodb_table" "latest_state" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"

  attribute {
    name = "device_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.tags
}

resource "aws_ssm_parameter" "runtime" {
  name = local.runtime_path
  type = "String"
  value = jsonencode({
    project                             = local.project
    device_id                           = local.device_id
    thing_name                          = aws_iot_thing.device.name
    mqtt_topic                          = local.mqtt_topic
    iot_rule_name                       = aws_iot_topic_rule.telemetry.name
    ingest_lambda_name                  = aws_lambda_function.ingest.function_name
    latest_state_table_name             = aws_dynamodb_table.latest_state.name
    twinmaker_workspace_name            = local.twin_workspace
    twinmaker_entity_name               = local.twin_entity
    twinmaker_component_name            = local.twin_component
    twinmaker_component_type            = local.twin_type
    device_certificate_authoritative    = tostring(local.device_cert_authoritative)
    device_id_is_data_only              = tostring(local.device_id_is_data_only)
    reject_device_authored_offline      = tostring(local.reject_device_offline)
    connectivity_state_server_derived   = tostring(local.server_derived_connectivity)
    server_replay_and_stale_enforcement = tostring(local.server_replay_stale)
    cloudwatch_log_retention_days       = local.cloudwatch_retention
  })

  overwrite = true
  tier      = "Standard"
}

output "runtime" {
  value = jsondecode(aws_ssm_parameter.runtime.value)
}

output "thing_name" {
  value = aws_iot_thing.device.name
}

output "bucket_table_name" {
  value = aws_dynamodb_table.latest_state.name
}
