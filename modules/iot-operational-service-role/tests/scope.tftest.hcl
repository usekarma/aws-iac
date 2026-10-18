mock_provider "aws" {}
override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "623155450153" }
}
run "m1_only_scope" {
  command = plan
  assert {
    condition     = output.trust_policy.Statement[0].Principal.Service == "cloudformation.amazonaws.com" && length(output.trust_policy.Statement) == 1
    error_message = "Only CloudFormation may assume this role, not IoT or human principals."
  }
  assert {
    condition     = output.handler_policy.Statement[0].Resource == "*" && output.handler_policy.Statement[0].Condition.StringEquals["aws:RequestTag/Experiment"] == "operational-telemetry"
    error_message = "Model creation wildcard must require M1 request tags."
  }
  assert {
    condition     = output.handler_policy.Statement[2].Condition.StringEquals["aws:ResourceTag/Project"] == "iot-digital-twin" && output.handler_policy.Statement[3].Condition.StringEquals["aws:ResourceTag/Experiment"] == "operational-telemetry"
    error_message = "Existing SiteWise objects require ownership tag fences."
  }
  assert {
    condition     = output.handler_policy.Statement[5].Resource == "arn:aws:iot:us-east-1:623155450153:rule/iot_digital_twin_operational_m1" && output.handler_policy.Statement[6].Resource == "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-routing" && output.handler_policy.Statement[6].Condition.StringEquals["iam:PassedToService"] == "iot.amazonaws.com"
    error_message = "Rule/PassRole must be exact; no producer or ATOM IAM permissions."
  }
  assert {
    condition     = alltrue([for s in slice(output.handler_policy.Statement, 0, 6) : s.Condition.StringEquals["aws:RequestedRegion"] == "us-east-1"]) && !contains(flatten([for s in output.handler_policy.Statement : s.Action]), "iot:Publish") && !contains(flatten([for s in output.handler_policy.Statement : s.Action]), "iotsitewise:BatchPutAssetPropertyValue")
    error_message = "Region fence required; service role must not gain runtime ingestion/MQTT."
  }
}
run "wrong_account" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "111111111111" }
  }
  expect_failures = [aws_iam_role.cloud_control]
}
