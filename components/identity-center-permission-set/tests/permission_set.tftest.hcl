mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "835990279085"
    }
  }
  mock_data "aws_ssm_parameter" {
    defaults = {
      value = file("../../examples/identity-center-owner.iac-plan-readonly.json")
    }
  }
}

variables {
  component_name = "identity-center-permission-set"
  nickname       = "owner-iac-plan-readonly"
}

run "reviewed_planning_permission_set" {
  command = plan
  assert {
    condition     = aws_ssoadmin_permission_set.permission_set.name == "IaCPlanReadOnly" && aws_ssoadmin_permission_set.permission_set.session_duration == "PT1H"
    error_message = "The reviewed permission set name and one-hour duration must be preserved."
  }
  assert {
    condition     = aws_ssoadmin_permission_set_inline_policy.inline_policy.inline_policy == jsonencode(jsondecode(file("../../examples/identity-center-owner.iac-plan-readonly.json")).inline_policy)
    error_message = "The policy must exactly preserve the reviewed declaration."
  }
  assert {
    condition     = length(aws_ssoadmin_account_assignment.assignment) == 1 && aws_ssoadmin_account_assignment.assignment["623155450153/USER/b4486448-d011-7037-9cfb-c16c43f591e1"].target_id == "623155450153" && aws_ssoadmin_account_assignment.assignment["623155450153/USER/b4486448-d011-7037-9cfb-c16c43f591e1"].principal_type == "USER"
    error_message = "Only the reviewed USER assignment into strall-dev may be declared."
  }
}

run "reject_wrong_caller" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "623155450153"
    }
  }
  expect_failures = [aws_ssoadmin_permission_set.permission_set]
}

run "reject_wrong_configured_owner" {
  command = plan
  override_data {
    target = data.aws_ssm_parameter.config[0]
    values = {
      value = jsonencode(merge(jsondecode(file("../../examples/identity-center-owner.iac-plan-readonly.json")), { administration_account_id = "623155450153" }))
    }
  }
  expect_failures = [aws_ssoadmin_permission_set.permission_set]
}

run "human_bootstrap_has_no_ssm_dependency" {
  command = plan
  variables {
    bootstrap_config_json = file("../../examples/identity-center-owner.iac-plan-readonly.json")
  }
  assert {
    condition     = length(data.aws_ssm_parameter.config) == 0 && aws_ssoadmin_permission_set.permission_set.name == "IaCPlanReadOnly"
    error_message = "The bootstrap declaration must not depend on published SSM inputs."
  }
}
