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
terraform {
  required_providers {
    aws   = { source = "hashicorp/aws", version = "= 6.69.1" }
    awscc = { source = "hashicorp/awscc", version = "= 1.106.0" }
  }
}
resource "awscc_iotsitewise_asset_model" "model" {
  asset_model_name       = "${local.prefix}-model"
  asset_model_properties = [{ name = "severity", logical_id = "Severity", data_type = "INTEGER", type = { type_name = "Measurement" } }]
  tags                   = [for k, v in local.tags : { key = k, value = v }]
  lifecycle {
    precondition {
      condition     = var.config.expected_account == var.account_id && var.config.region == var.region && var.config.cloudformation_role_arn != null && can(regex("^[0-9a-f]{64}$", var.config.expected_principal)) && startswith(coalesce(var.config.cloudformation_role_arn, "unresolved"), "arn:${var.partition}:iam::${var.account_id}:role/") && !can(var.config.planning_dependencies)
      error_message = "Resolve reviewed account/region, producer principal and CloudFormation role before planning."
    }
  }

}
resource "awscc_iotsitewise_asset" "asset" {
  asset_name       = "${local.prefix}-asset-000"
  asset_model_id   = awscc_iotsitewise_asset_model.model.asset_model_id
  asset_properties = [{ logical_id = "Severity", alias = local.alias, notification_state = "DISABLED" }]
  tags             = [for k, v in local.tags : { key = k, value = v }]
}
resource "awscc_iot_topic_rule" "telemetry" {
  rule_name = local.rule_name
  topic_rule_payload = {
    aws_iot_sql_version = "2016-03-23"
    rule_disabled       = false
    sql                 = local.sql
    actions = [{ iot_site_wise = {
      role_arn = aws_iam_role.routing.arn
      put_asset_property_value_entries = [{ property_alias = local.alias, entry_id = "$${run_id}-$${sequence}",
        property_values = [{ quality = "GOOD", value = { integer_value = "$${severity}" }, timestamp = { time_in_seconds = "$${event_time_seconds}", offset_in_nanos = "0" } }]
      }]
    } }]
    error_action = { cloudwatch_logs = { log_group_name = aws_cloudwatch_log_group.errors.name, role_arn = aws_iam_role.routing.arn } }
  }
  depends_on = [awscc_iotsitewise_asset.asset, aws_iam_role_policy.routing]
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
    asset_id = awscc_iotsitewise_asset.asset.asset_id, model_id = awscc_iotsitewise_asset_model.model.asset_model_id,
  property_alias = local.alias, topic = local.topic, client_id = aws_iot_thing.producer.name }
}
output "test_contract" {
  value = { model = awscc_iotsitewise_asset_model.model, asset = awscc_iotsitewise_asset.asset, rule = awscc_iot_topic_rule.telemetry, policy = jsondecode(aws_iam_role_policy.routing.policy), sql = local.sql }
}
