mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "835990279085" }
  }
  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-7223e8cbef5c5b91/ps-1234567890abcdef"
    }
  }
}

variables {
  component_name        = "identity-center-permission-set"
  nickname              = "owner-iac-plan-readonly"
  bootstrap_config_json = file("../../examples/identity-center-owner.iac-plan-readonly.json")
}

run "synthetic_existing_owner" {
  # Mock-provider apply seeds disposable TEST state, never the retained real state.
  command = apply
}

run "single_config_read_update" {
  command = plan
  variables {
    bootstrap_config_json = file("../../examples/identity-center-owner.iac-plan-readonly.config-read.json")
  }
  assert {
    condition     = aws_ssoadmin_permission_set_inline_policy.inline_policy.inline_policy == jsonencode(jsondecode(file("../../examples/identity-center-owner.iac-plan-readonly.config-read.json")).inline_policy)
    error_message = "Only the reviewed maintenance policy may be proposed."
  }
  assert {
    condition     = aws_ssoadmin_permission_set.permission_set.name == "IaCPlanReadOnly" && aws_ssoadmin_permission_set.permission_set.session_duration == "PT1H" && aws_ssoadmin_account_assignment.assignment["623155450153/USER/b4486448-d011-7037-9cfb-c16c43f591e1"].target_id == "623155450153"
    error_message = "Permission set/session/assignment must remain unchanged."
  }
}
