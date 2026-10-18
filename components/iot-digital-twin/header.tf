terraform {
  backend "s3" {}
  required_providers {
    aws   = { source = "hashicorp/aws", version = "= 6.69.1" }
    awscc = { source = "hashicorp/awscc", version = "= 1.106.0" }
  }
}
variable "region" { type = string }
variable "component_name" { type = string }
variable "nickname" { type = string }
variable "iac_prefix" {
  type    = string
  default = "/iac"
}
provider "aws" { region = var.region }
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_ssm_parameter" "config" {
  name = "${var.iac_prefix}/${var.component_name}/${var.nickname}/config"
}
locals {
  config                = nonsensitive(jsondecode(data.aws_ssm_parameter.config.value))
  mode                  = try(local.config.mode, "durable-simulator")
  deployment_stage      = try(local.config.deployment_stage, "external-role")
  bootstrap             = local.mode == "operational-telemetry" && local.deployment_stage == "service-role-bootstrap"
  managed_cloud_control = local.mode == "operational-telemetry" && contains(["service-role-bootstrap", "operational"], local.deployment_stage)
}

provider "awscc" {
  region = var.region
  # Cloud Control service role, NOT an assume_role for Terraform's caller.
  role_arn = local.bootstrap ? null : try(local.config.cloudformation_role_arn, null)
}

# Stage 2 reads the already-created role; bootstrap does not query an absent role.
data "aws_iam_role" "verified_cloud_control" {
  count = local.managed_cloud_control && !local.bootstrap ? 1 : 0
  name  = "iot-digital-twin-operational-m1-cloud-control"
}
