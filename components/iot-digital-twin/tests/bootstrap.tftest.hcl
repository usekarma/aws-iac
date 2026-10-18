mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "623155450153" } }
  mock_data "aws_iam_role" { defaults = { arn = "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_data "aws_ssm_parameter" {
    defaults = { value = jsonencode({ mode = "operational-telemetry", deployment_stage = "service-role-bootstrap", awscc_request_tags_verified = false, region = "us-east-1", expected_account = "623155450153", expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", cloudformation_role_arn = null }) }
  }
}
mock_provider "awscc" {}
run "bootstrap_only" {
  command = plan
  variables {
    region         = "us-east-1"
    component_name = "iot-digital-twin"
    nickname       = "operational-demo"
  }
  assert {
    condition     = length(module.cloud_control) == 1 && length(module.operational) == 0 && length(module.durable) == 0 && length(aws_ssm_parameter.runtime) == 0
    error_message = "Stage 1 must create only the role, policy and local mode guard, no AWSCC/runtime."
  }
}
run "unverified_stage_two_rejected" {
  command = plan
  variables {
    region         = "us-east-1"
    component_name = "iot-digital-twin"
    nickname       = "operational-demo"
  }
  override_data {
    target = data.aws_ssm_parameter.config
    values = { value = jsonencode({ mode = "operational-telemetry", deployment_stage = "operational", awscc_request_tags_verified = false, region = "us-east-1", expected_account = "623155450153", expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", cloudformation_role_arn = "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control" }) }
  }
  expect_failures = [terraform_data.mode]
}

run "operational_stage_keeps_role_address" {
  command = plan
  variables {
    region         = "us-east-1"
    component_name = "iot-digital-twin"
    nickname       = "operational-demo"
  }
  override_data {
    target = data.aws_ssm_parameter.config
    values = { value = jsonencode({ mode = "operational-telemetry", deployment_stage = "operational", awscc_request_tags_verified = true, region = "us-east-1", expected_account = "623155450153", expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", cloudformation_role_arn = "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control" }) }
  }
  assert {
    condition     = length(module.cloud_control) == 1 && length(module.operational) == 1 && length(module.durable) == 0 && length(aws_ssm_parameter.runtime) == 1
    error_message = "Stage 2 retains managed role and enables only operational resources."
  }
}
