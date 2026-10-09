terraform {
  # 🚨 DO NOT MODIFY THIS BACKEND BLOCK!
  # This empty backend block is required for compatibility with Terragrunt.
  # Terragrunt dynamically injects the actual S3/DynamoDB configuration.
  # Any changes here will be ignored — and could break Terragrunt compatibility.

  backend "s3" {}
}

provider "aws" {
  region = var.region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

data "aws_ssm_parameter" "config" {
  count = var.plan_config_json == null ? 1 : 0
  name  = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
}

locals {
  config = jsondecode(var.plan_config_json == null ? try(nonsensitive(data.aws_ssm_parameter.config[0].value), "{}") : var.plan_config_json)

  tags = merge(
    {
      Project   = try(local.config.project, var.nickname)
      Component = var.component_name
    },
    try(local.config.tags, {})
  )

  config_path  = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
  runtime_path = "${var.iac_prefix}/${var.component_name}/${var.nickname}/runtime"
}

variable "plan_config_json" {
  type        = string
  default     = null
  description = "Unpublished configuration for plan review only. Human execution must publish reviewed aws-config inputs and regenerate the plan."

  validation {
    condition     = var.plan_config_json == null ? true : can(jsondecode(var.plan_config_json).bucket_name)
    error_message = "Plan configuration must be a JSON object containing bucket_name."
  }
}

moved {
  from = data.aws_ssm_parameter.config
  to   = data.aws_ssm_parameter.config[0]
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
