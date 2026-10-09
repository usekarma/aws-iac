terraform {
  # 🚨 DO NOT MODIFY THIS BACKEND BLOCK!
  # This empty backend block is required for compatibility with Terragrunt.
  # Terragrunt dynamically injects the actual S3/DynamoDB configuration.
  backend "s3" {}
}

provider "aws" {
  region = var.region
}

data "aws_ssm_parameter" "config" {
  name = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
}

locals {
  config = try(nonsensitive(jsondecode(data.aws_ssm_parameter.config.value)), {})

  tags = merge(
    {
      Project   = try(local.config.project, var.nickname)
      Component = var.component_name
    },
    try(local.config.tags, {})
  )

  config_path  = data.aws_ssm_parameter.config.name
  runtime_path = "${var.iac_prefix}/${var.component_name}/${var.nickname}/runtime"

  project                        = try(local.config.project, var.nickname)
  device_id                      = try(local.config.device_id, var.nickname)
  thing_name                     = try(local.config.thing_name, "${var.nickname}-device")
  mqtt_topic                     = try(local.config.mqtt_topic, "devices/${var.nickname}/telemetry")
  iot_rule_name                  = try(local.config.iot_rule_name, "${var.nickname}-telemetry")
  lambda_name                    = try(local.config.ingest_lambda_name, "${var.nickname}-ingest")
  table_name                     = try(local.config.latest_state_table_name, "${var.nickname}-latest-state")
  twin_workspace                 = try(local.config.twinmaker_workspace_name, "")
  twin_entity                    = try(local.config.twinmaker_entity_name, "")
  twin_component                 = try(local.config.twinmaker_component_name, "")
  twin_type                      = try(local.config.twinmaker_component_type, "")
  telemetry_rate_hz              = try(local.config.telemetry_rate_hz, 1.0)
  offline_timeout_seconds        = try(local.config.offline_timeout_seconds, 30)
  max_clock_skew_seconds         = try(local.config.max_clock_skew_seconds, 10)
  max_retry_attempts             = try(local.config.max_retry_attempts, 0)
  least_privilege_iam            = try(local.config.least_privilege_iam, true)
  no_broad_permission_fallback   = try(local.config.no_broad_permission_fallback, true)
  device_cert_authoritative      = try(local.config.device_certificate_authoritative, true)
  device_id_is_data_only         = try(local.config.device_id_is_data_only, true)
  reject_device_authored_offline = try(local.config.reject_device_authored_offline, true)
  server_derived_connectivity    = try(local.config.connectivity_state_server_derived, true)
  server_replay_stale            = try(local.config.server_replay_and_stale_enforcement, true)
  cloudwatch_retention           = try(local.config.cloudwatch_log_retention_days, 30)

  # This repo's Terraform provider does not expose aws_iottwinmaker_* resources.
  # We keep the DynamoDB latest-state design and make the TwinMaker connector
  # status explicit instead of silently treating the config as deployable.
  twinmaker_status = "deferred-until-provider-support-or-aws-api-integration"
}

variable "region" {
  type        = string
  description = "AWS region to use"
  default     = "us-east-1"
}

variable "component_name" {
  type        = string
  description = "Name of the component"
}

variable "nickname" {
  type        = string
  description = "Nickname"
}

variable "iac_prefix" {
  type    = string
  default = "/iac"
}
