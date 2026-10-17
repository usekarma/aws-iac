terraform {
  backend "s3" {}
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.69.1" }
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
  config = nonsensitive(jsondecode(data.aws_ssm_parameter.config.value))
  mode   = try(local.config.mode, "durable-simulator")
}
