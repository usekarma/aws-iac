resource "aws_ssoadmin_permission_set" "permission_set" {
  name             = local.config.permission_set_name
  description      = local.config.description
  instance_arn     = local.config.instance_arn
  session_duration = local.config.session_duration
  tags             = local.tags

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == var.administration_account_id
      error_message = "Caller must match the independently verified administration account."
    }
    precondition {
      condition     = local.config.administration_account_id == var.administration_account_id
      error_message = "Configuration administration account must match the provider target."
    }
    precondition {
      condition     = can(regex("^arn:aws:sso:::instance/ssoins-[A-Za-z0-9]+$", local.config.instance_arn))
      error_message = "Supply an existing Identity Center instance ARN."
    }
    precondition {
      condition     = can(local.config.inline_policy.Statement) && try(local.config.inline_policy.Version == "2012-10-17", false)
      error_message = "Inline policy must be an IAM policy object using Version 2012-10-17."
    }
  }
}

resource "aws_ssoadmin_permission_set_inline_policy" "inline_policy" {
  instance_arn       = local.config.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.permission_set.arn
  inline_policy      = jsonencode(local.config.inline_policy)
}

resource "aws_ssoadmin_account_assignment" "assignment" {
  for_each = local.assignments

  instance_arn       = local.config.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.permission_set.arn
  target_id          = each.value.target_account_id
  target_type        = "AWS_ACCOUNT"
  principal_type     = each.value.principal_type
  principal_id       = each.value.principal_id

  # Provision the inline policy before granting account access.
  depends_on = [aws_ssoadmin_permission_set_inline_policy.inline_policy]

  lifecycle {
    precondition {
      condition     = contains(["USER", "GROUP"], each.value.principal_type) && can(regex("^[0-9]{12}$", each.value.target_account_id)) && length(trimspace(each.value.principal_id)) > 0
      error_message = "Assignments require USER/GROUP, a 12-digit target account, and an existing principal ID."
    }
  }
}

resource "aws_ssm_parameter" "runtime" {
  name = local.runtime_path
  type = "String"
  value = jsonencode({
    permission_set_arn = aws_ssoadmin_permission_set.permission_set.arn
    instance_arn       = local.config.instance_arn
    assignments        = local.config.assignments
  })
  overwrite = true
  tier      = "Standard"
  tags      = local.tags

  depends_on = [aws_ssoadmin_account_assignment.assignment]
}
