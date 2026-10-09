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

  project        = try(local.config.project, var.nickname)
  device_id      = try(local.config.device_id, var.nickname)
  thing_name     = try(local.config.thing_name, "${var.nickname}-device")
  mqtt_topic     = try(local.config.mqtt_topic, "devices/${var.nickname}/telemetry")
  iot_rule_name  = try(local.config.iot_rule_name, "${var.nickname}-telemetry")
  lambda_name    = try(local.config.ingest_lambda_name, "${var.nickname}-ingest")
  table_name     = try(local.config.latest_state_table_name, "${var.nickname}-latest-state")
  twin_workspace = try(local.config.twinmaker_workspace_name, "${var.nickname}-workspace")
  twin_entity    = try(local.config.twinmaker_entity_name, "${var.nickname}-entity")
  twin_component = try(local.config.twinmaker_component_name, "${var.nickname}-component")
  twin_type      = try(local.config.twinmaker_component_type, "${var.nickname}-component-type")
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
