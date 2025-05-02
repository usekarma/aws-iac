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
  type        = string
  default     = "/iac"
}
