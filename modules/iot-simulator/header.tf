variable "region" { type = string }
variable "config" { type = any }
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
locals {
  config        = var.config
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
