mock_provider "awscc" {
  mock_resource "awscc_iotsitewise_asset_model" { defaults = { asset_model_id = "22222222-2222-2222-2222-222222222222" } }
  mock_resource "awscc_iotsitewise_asset" { defaults = { asset_id = "11111111-1111-1111-1111-111111111111" } }
}
mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "000000000000" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_data "aws_ssm_parameter" {
    defaults = { value = jsonencode({ mode = "operational-telemetry", region = "us-east-1", expected_account = "000000000000", expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", cloudformation_role_arn = "arn:aws:iam::000000000000:role/synthetic" }) }
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
    condition     = module.operational[0].test_contract.model.asset_model_properties[0].data_type == "INTEGER" && module.operational[0].test_contract.asset.asset_properties[0].logical_id == "Severity"
    error_message = "AWSCC must bind one INTEGER measurement by logical ID."
  }
  assert {
    condition     = length(module.operational[0].test_contract.model.asset_model_properties) == 1 && module.operational[0].test_contract.model.asset_model_properties[0].type.type_name == "Measurement" && module.operational[0].test_contract.model.asset_model_properties[0].logical_id == "Severity" && module.operational[0].test_contract.asset.asset_model_id == module.operational[0].runtime.model_id
    error_message = "Exactly one measurement must bind the asset to its model."
  }
  assert {
    condition     = module.operational[0].test_contract.asset.asset_properties[0].alias == module.operational[0].runtime.property_alias && module.operational[0].test_contract.asset.asset_properties[0].notification_state == "DISABLED"
    error_message = "The exact alias and disabled notifications must be preserved."
  }
  assert {
    condition     = module.operational[0].test_contract.rule.rule_name == "iot_digital_twin_operational_m1" && module.operational[0].test_contract.rule.topic_rule_payload.actions[0].iot_site_wise.put_asset_property_value_entries[0].property_alias == module.operational[0].runtime.property_alias && module.operational[0].test_contract.rule.topic_rule_payload.actions[0].iot_site_wise.put_asset_property_value_entries[0].property_values[0].quality == "GOOD"
    error_message = "Native routing must retain the fixed alias and GOOD TQV contract."
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
