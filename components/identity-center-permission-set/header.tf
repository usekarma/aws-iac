terraform {
  backend "s3" {}
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.administration_account_id]
}

variable "administration_account_id" {
  type        = string
  description = "Independently verified Identity Center administration account. The repository runner currently permits only owner account 835990279085."
  default     = "835990279085"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.administration_account_id))
    error_message = "Administration account ID must contain exactly 12 digits."
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "component_name" {
  type = string
}

variable "nickname" {
  type = string
}

variable "iac_prefix" {
  type    = string
  default = "/iac"
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "config" {
  name = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
}

locals {
  config       = jsondecode(nonsensitive(data.aws_ssm_parameter.config.value))
  runtime_path = "${var.iac_prefix}/${var.component_name}/${var.nickname}/runtime"
  assignments = {
    for assignment in local.config.assignments :
    "${assignment.target_account_id}/${assignment.principal_type}/${assignment.principal_id}" => assignment
  }
  tags = merge({
    Project   = try(local.config.project, var.nickname)
    Component = var.component_name
  }, try(local.config.tags, {}))
}
