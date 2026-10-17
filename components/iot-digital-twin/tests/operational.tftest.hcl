mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "000000000000" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_data "aws_ssm_parameter" {
    defaults = { value = jsonencode({ mode = "operational-telemetry", region = "us-east-1", expected_account = "000000000000", expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", cloudformation_role_arn = "arn:aws:iam::000000000000:role/synthetic" }) }
  }
  mock_resource "aws_cloudformation_stack" {
    defaults = { outputs = { AssetId = "11111111-1111-1111-1111-111111111111", ModelId = "22222222-2222-2222-2222-222222222222" } }
  }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::000000000000:role/synthetic" } }
}
run "one_property_routing" {
  command = apply
  variables {
    region         = "us-east-1"
    component_name = "iot-digital-twin"
    nickname       = "operational-demo"
  }
  assert {
    condition     = length(module.durable) == 0 && length(module.operational) == 1
    error_message = "Operational mode must not provision durable simulator resources."
  }
  assert {
    condition     = module.operational[0].test_contract.template.Resources.Model.Properties.AssetModelProperties[0].DataType == "INTEGER" && module.operational[0].test_contract.template.Resources.Asset.Properties.AssetProperties[0].LogicalId == "Severity"
    error_message = "CloudFormation must bind one INTEGER measurement by logical ID."
  }
  assert {
    condition     = module.operational[0].test_contract.policy.Statement[0].Condition.StringEquals["iotsitewise:propertyAlias"] == "/adage/iot-digital-twin/operational-demo/asset-000/severity"
    error_message = "Alias-based time-series writes require the exact alias fence."
  }
  assert {
    condition     = strcontains(module.operational[0].test_contract.sql, "principal()") && strcontains(module.operational[0].test_contract.sql, "sequence = tick")
    error_message = "Rule must check producer authority and tick contract."
  }
}
