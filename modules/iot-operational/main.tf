variable "config" { type = any }
variable "region" { type = string }
variable "account_id" { type = string }
variable "partition" { type = string }
locals {
  prefix    = "iot-digital-twin-operational-m1"
  alias     = "/adage/iot-digital-twin/operational-demo/asset-000/severity"
  topic     = "adage/iot-digital-twin/operational-demo/asset-000/telemetry"
  rule_name = "iot_digital_twin_operational_m1"
  rule_arn  = "arn:${var.partition}:iot:${var.region}:${var.account_id}:rule/${local.rule_name}"
  tags      = { Project = "iot-digital-twin", Experiment = "operational-telemetry", Environment = "sandbox" }
  sql       = "SELECT * FROM '${local.topic}' WHERE principal() = '${var.config.expected_principal}' AND schema_version = 1 AND synthetic = true AND asset_id = 'asset-000' AND epoch = 1 AND sequence = tick AND tick >= 1 AND tick <= 20 AND severity >= 0 AND severity <= 2 AND floor(severity) = severity AND event_time_nanos = 0"
}
resource "aws_cloudformation_stack" "sitewise" {
  name               = local.prefix
  iam_role_arn       = var.config.cloudformation_role_arn
  timeout_in_minutes = 15
  tags               = local.tags
  template_body = jsonencode({
    AWSTemplateFormatVersion = "2010-09-09"
    Resources = {
      Model = {
        Type = "AWS::IoTSiteWise::AssetModel"
        Properties = {
          AssetModelName       = "${local.prefix}-model"
          AssetModelProperties = [{ Name = "severity", LogicalId = "Severity", DataType = "INTEGER", Type = { TypeName = "Measurement" } }]
          Tags                 = [for k, v in local.tags : { Key = k, Value = v }]
        }
      }
      Asset = {
        Type = "AWS::IoTSiteWise::Asset"
        Properties = {
          AssetName       = "${local.prefix}-asset-000"
          AssetModelId    = { "Fn::GetAtt" = ["Model", "AssetModelId"] }
          AssetProperties = [{ LogicalId = "Severity", Alias = local.alias, NotificationState = "DISABLED" }]
          Tags            = [for k, v in local.tags : { Key = k, Value = v }]
        }
      }
      Routing = {
        Type      = "AWS::IoT::TopicRule"
        DependsOn = "Asset"
        Properties = {
          RuleName = local.rule_name
          TopicRulePayload = {
            AwsIotSqlVersion = "2016-03-23"
            RuleDisabled     = false
            Sql              = local.sql
            Actions = [{ IotSiteWise = {
              RoleArn = aws_iam_role.routing.arn
              PutAssetPropertyValueEntries = [{ PropertyAlias = local.alias, EntryId = "$${run_id}-$${sequence}",
                PropertyValues = [{ Quality = "GOOD", Value = { IntegerValue = "$${severity}" }, Timestamp = { TimeInSeconds = "$${event_time_seconds}", OffsetInNanos = "0" } }]
              }]
            } }]
            ErrorAction = { CloudwatchLogs = { LogGroupName = aws_cloudwatch_log_group.errors.name, RoleArn = aws_iam_role.routing.arn } }
          }
        }
      }
    }
    Outputs = {
      AssetId = { Value = { "Fn::GetAtt" = ["Asset", "AssetId"] } }
      ModelId = { Value = { "Fn::GetAtt" = ["Model", "AssetModelId"] } }
    }
  })
  depends_on = [aws_iam_role_policy.routing]
  lifecycle {
    precondition {
      condition     = var.config.expected_account == var.account_id && var.config.region == var.region && var.config.cloudformation_role_arn != null && can(regex("^[0-9a-f]{64}$", var.config.expected_principal)) && startswith(coalesce(var.config.cloudformation_role_arn, "unresolved"), "arn:${var.partition}:iam::${var.account_id}:role/") && !can(var.config.planning_dependencies)
      error_message = "Resolve reviewed account/region, producer principal and CloudFormation role before planning."
    }
  }
}
resource "aws_iot_thing" "producer" {
  name       = "adage-operational-m1"
  attributes = { project = "iot-digital-twin", synthetic = "true" }
}
resource "aws_iot_policy" "producer" {
  name = "${local.prefix}-publish"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "iot:Connect", Resource = "arn:${var.partition}:iot:${var.region}:${var.account_id}:client/adage-operational-m1" },
    { Effect = "Allow", Action = "iot:Publish", Resource = "arn:${var.partition}:iot:${var.region}:${var.account_id}:topic/${local.topic}" }
  ] })
}
# No certificate/key creation or attachment: separately authorized credential lifecycle.
resource "aws_cloudwatch_log_group" "errors" {
  name              = "/aws/iot/${local.prefix}-errors"
  retention_in_days = 7
  tags              = local.tags
}
resource "aws_iam_role" "routing" {
  name = "${local.prefix}-routing"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "iot.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = { StringEquals = { "aws:SourceAccount" = var.account_id }, ArnEquals = { "aws:SourceArn" = local.rule_arn } }
  }] })
  tags = local.tags
}
resource "aws_iam_role_policy" "routing" {
  role = aws_iam_role.routing.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    # Alias-based ingestion authorizes time-series, not asset ARNs. Fixed alias fences this wildcard.
    { Effect = "Allow", Action = "iotsitewise:BatchPutAssetPropertyValue", Resource = "arn:${var.partition}:iotsitewise:${var.region}:${var.account_id}:time-series/*",
    Condition = { StringEquals = { "iotsitewise:propertyAlias" = local.alias } } },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.errors.arn}:*" }
  ] })
}
output "runtime" {
  value = { schema_version = 1, mode = "operational-telemetry", region = var.region, account_id = var.account_id,
    asset_id = aws_cloudformation_stack.sitewise.outputs["AssetId"], model_id = aws_cloudformation_stack.sitewise.outputs["ModelId"],
  property_alias = local.alias, topic = local.topic, client_id = aws_iot_thing.producer.name }
}
output "test_contract" {
  value = { template = jsondecode(aws_cloudformation_stack.sitewise.template_body), policy = jsondecode(aws_iam_role_policy.routing.policy), sql = local.sql }
}
