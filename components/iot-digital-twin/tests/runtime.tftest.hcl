mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = {
      value = jsonencode({
        model_commit       = "ffffffffffffffffffffffffffffffffffffffff"
        active_session     = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        expected_principal = "synthetic-test-principal"
        artifact = {
          s3_bucket         = "synthetic-artifact-bucket"
          s3_key            = "iot-digital-twin-simulator.zip"
          s3_object_version = "synthetic-version"
          source_code_hash  = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        }
      })
    }
  }
  mock_data "aws_caller_identity" { defaults = { account_id = "000000000000" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_resource "aws_lambda_function" { defaults = { arn = "arn:aws:lambda:us-east-1:000000000000:function:synthetic-test" } }
  mock_resource "aws_iot_topic_rule" { defaults = { arn = "arn:aws:iot:us-east-1:000000000000:rule/iot_digital_twin_simulator_reset" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::000000000000:role/synthetic-test" } }
  mock_resource "aws_dynamodb_table" { defaults = { arn = "arn:aws:dynamodb:us-east-1:000000000000:table/iot-digital-twin-simulator-state" } }
}
run "scoped_runtime" {
  # Mock-provider evaluation only: no AWS API or infrastructure operation.
  command = apply
  variables {
    region         = "us-east-1"
    component_name = "iot-digital-twin-simulator"
    nickname       = "synthetic-test"
  }
  assert {
    condition = aws_dynamodb_table.state.tags.Project == "iot-digital-twin" && aws_dynamodb_table.state.tags.Experiment == "atom-lite-simulator"
    error_message = "Canonical project and experiment tags must remain distinct."
  }
  assert {
    condition     = aws_lambda_function.runtime["runner"].reserved_concurrent_executions == 1 && aws_lambda_function.runtime["runner"].timeout == 210
    error_message = "Runner concurrency and invocation bounds must remain explicit."
  }
  assert {
    condition     = aws_lambda_function.runtime["reset"].handler == "app.reset_handler" && aws_lambda_permission.reset_rule.principal == "iot.amazonaws.com"
    error_message = "Reset handler must be bound to the scoped IoT invocation path."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role_policy.runtime["runner"].policy).Statement) == 2 && length(jsondecode(aws_iam_role_policy.runtime["reset"].policy).Statement) == 3
    error_message = "Only reset role receives IoT publish; runner only storage and logging."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime["reset"].policy).Statement[0].Condition["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"][0] == "SESSION#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    error_message = "Storage access must be fenced to the explicitly configured session."
  }
}
