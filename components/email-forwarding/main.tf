terraform {
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

module "email_forwarding" {
  source = "git::https://github.com/arithmetric/aws-lambda-ses-forwarder.git?ref=master"

  # Variables that must be passed:
  domain               = var.domain
  forward_to_addresses = var.forward_to_addresses
  from_email           = var.from_email
}

resource "aws_ses_domain_identity" "domain" {
  domain = var.domain
}

resource "aws_ses_domain_dkim" "dkim" {
  domain = aws_ses_domain_identity.domain.domain
}

resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = "${var.domain}-rule-set"
}

resource "aws_ses_receipt_rule" "forwarding" {
  name          = "Forward-${var.domain}"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = [var.domain]
  enabled       = true
  scan_enabled  = true

  lambda_action {
    function_arn    = aws_lambda_function.email_forwarder.arn
    invocation_type = "Event"
    position        = 1
  }

  depends_on = [aws_lambda_permission.allow_ses]
}

resource "aws_lambda_permission" "allow_ses" {
  statement_id  = "AllowExecutionFromSES"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.email_forwarder.function_name
  principal     = "ses.amazonaws.com"
  source_arn    = aws_ses_receipt_rule.forwarding.arn
}
