data "aws_caller_identity" "current" {}

resource "aws_iot_thing" "device" {
  name = local.thing_name

  attributes = {
    project                        = local.project
    device_id                      = local.device_id
    mqtt_topic                     = local.mqtt_topic
    server_derived_connectivity    = tostring(local.server_derived_connectivity)
    device_id_is_data_only         = tostring(local.device_id_is_data_only)
    reject_device_authored_offline = tostring(local.reject_device_authored_offline)
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
      }
    ]
  })
}

resource "terraform_data" "config_contract" {
  input = {
    device_id                        = local.device_id
    telemetry_rate_hz                = local.telemetry_rate_hz
    offline_timeout_seconds          = local.offline_timeout_seconds
    max_clock_skew_seconds           = local.max_clock_skew_seconds
    max_retry_attempts               = local.max_retry_attempts
    least_privilege_iam              = local.least_privilege_iam
    no_broad_permission_fallback     = local.no_broad_permission_fallback
    device_certificate_authoritative = local.device_cert_authoritative
    device_id_is_data_only           = local.device_id_is_data_only
    reject_device_authored_offline   = local.reject_device_authored_offline
  }

  lifecycle {
    precondition {
      condition     = local.least_privilege_iam == true
      error_message = "least_privilege_iam must be true; broad or implicit IAM fallback is not allowed in this prototype."
    }
    precondition {
      condition     = local.no_broad_permission_fallback == true
      error_message = "no_broad_permission_fallback must be true; do not permit wildcard fallback access."
    }
    precondition {
      condition     = local.max_retry_attempts >= 0
      error_message = "max_retry_attempts must be non-negative."
    }
    precondition {
      condition     = local.telemetry_rate_hz > 0
      error_message = "telemetry_rate_hz must be greater than zero."
    }
    precondition {
      condition     = local.offline_timeout_seconds > 0
      error_message = "offline_timeout_seconds must be greater than zero."
    }
    precondition {
      condition     = local.max_clock_skew_seconds >= 0
      error_message = "max_clock_skew_seconds must be zero or greater."
    }
    precondition {
      condition     = local.device_cert_authoritative == true
      error_message = "device_certificate_authoritative must remain true; payload device_id is not the trust anchor."
    }
  }
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
        Sid    = "LatestStateTable"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:ConditionCheckItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.latest_state.arn
      },
      {
        Sid    = "SsmConfigReadOnly"
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
      DEVICE_ID                        = local.device_id
      THING_NAME                       = local.thing_name
      MQTT_TOPIC                       = local.mqtt_topic
      IAC_PREFIX                       = var.iac_prefix
      STATE_TABLE                      = aws_dynamodb_table.latest_state.name
      PROJECT_NAME                     = local.project
      SERVER_REPLAY                    = tostring(local.server_replay_stale)
      CONNECTIVITY                     = tostring(local.server_derived_connectivity)
      DEVICE_CERTIFICATE_AUTHORITATIVE = tostring(local.device_cert_authoritative)
      DEVICE_ID_IS_DATA_ONLY           = tostring(local.device_id_is_data_only)
      REJECT_DEVICE_AUTHORED_OFFLINE   = tostring(local.reject_device_authored_offline)
      TELEMETRY_RATE_HZ                = tostring(local.telemetry_rate_hz)
      OFFLINE_TIMEOUT_SECONDS          = tostring(local.offline_timeout_seconds)
      MAX_CLOCK_SKEW_SECONDS           = tostring(local.max_clock_skew_seconds)
      MAX_RETRY_ATTEMPTS               = tostring(local.max_retry_attempts)
      STATE_ATTRIBUTE_LAST_SEQUENCE    = "last_sequence"
      STATE_ATTRIBUTE_LAST_SEEN_AT     = "last_seen_at"
      STATE_ATTRIBUTE_LAST_STATUS      = "last_status"
      TRUSTED_PRINCIPAL_FIELD          = "principal"
      TRUSTED_TOPIC_FIELD              = "topic"
      TWINMAKER_STATUS                 = local.twinmaker_status
      TWINMAKER_WORKSPACE_NAME         = local.twin_workspace
      TWINMAKER_ENTITY_NAME            = local.twin_entity
      TWINMAKER_COMPONENT_NAME         = local.twin_component
      TWINMAKER_COMPONENT_TYPE         = local.twin_type
    }
  }

  tags = local.tags
}

resource "aws_lambda_permission" "iot_trigger" {
  statement_id   = "AllowExecutionFromIoTTopicRule"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.ingest.function_name
  principal      = "iot.amazonaws.com"
  source_arn     = aws_iot_topic_rule.telemetry.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_iot_topic_rule" "telemetry" {
  name        = local.iot_rule_name
  enabled     = true
  sql         = "SELECT *, principal() AS principal, topic() AS topic FROM '${local.mqtt_topic}'"
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

# The Lambda must persist last accepted sequence and timestamp in DynamoDB rather
# than relying on in-memory state. The conditional update logic should reject
# duplicate/replay payloads and stale overwrites using the item's sequence/time.
resource "aws_dynamodb_table" "latest_state" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"

  attribute {
    name = "device_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
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
    server_side_state_strategy          = "dynamodb-item-conditionals"
    last_sequence_attribute             = "last_sequence"
    last_seen_at_attribute              = "last_seen_at"
    replay_rejection                    = "enabled"
    stale_overwrite_prevention          = "enabled"
    trusted_principal_source            = "aws_iot_topic_rule.principal()"
    device_certificate_authoritative    = tostring(local.device_cert_authoritative)
    device_id_is_data_only              = tostring(local.device_id_is_data_only)
    reject_device_authored_offline      = tostring(local.reject_device_authored_offline)
    connectivity_state_server_derived   = tostring(local.server_derived_connectivity)
    server_replay_and_stale_enforcement = tostring(local.server_replay_stale)
    cloudwatch_log_retention_days       = local.cloudwatch_retention
    twinmaker_status                    = local.twinmaker_status
    twinmaker_workspace_name            = local.twin_workspace
    twinmaker_entity_name               = local.twin_entity
    twinmaker_component_name            = local.twin_component
    twinmaker_component_type            = local.twin_type
    telemetry_rate_hz                   = local.telemetry_rate_hz
    offline_timeout_seconds             = local.offline_timeout_seconds
    max_clock_skew_seconds              = local.max_clock_skew_seconds
    max_retry_attempts                  = local.max_retry_attempts
    least_privilege_iam                 = local.least_privilege_iam
    no_broad_permission_fallback        = local.no_broad_permission_fallback
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

output "latest_state_table_name" {
  value = aws_dynamodb_table.latest_state.name
}

output "twinmaker_status" {
  value = local.twinmaker_status
}
