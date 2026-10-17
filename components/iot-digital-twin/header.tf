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
  config        = nonsensitive(jsondecode(data.aws_ssm_parameter.config.value))
  artifact      = local.config.artifact
  table_name    = "iot-digital-twin-simulator-state"
  request_topic = "devices/atom-lite-001/demo/reset/request"
  ack_topic     = "devices/atom-lite-001/demo/reset/ack"
  functions = {
    runner = { name = "iot-digital-twin-simulator-runner", handler = "app.runner_handler", timeout = 210 }
    reset  = { name = "iot-digital-twin-simulator-reset", handler = "app.reset_handler", timeout = 10 }
  }
  tags = { Project = "iot-digital-twin", Experiment = "atom-lite-simulator", Environment = "sandbox" }
}
