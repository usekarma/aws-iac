data "external" "resolved" {
  program = ["python3", "${path.module}/nickname_resolver.py"]
  query = {
    iac_base  = var.iac_prefix
    component = var.component_name
    nickname  = var.nickname
  }
}

locals {
  api_name             = local.config.api_name
  openapi_definition   = data.external.resolved.result.openapi_definition
  lambda_integrations  = try(data.external.resolved.result.lambda_integrations, {})
  stage_name           = try(local.config.stage_name, "v1")
  domain_name          = try(local.config.domain_name, null)
  route53_zone_name    = try(local.config.route53_zone_name, null)

  enable_custom_domain = local.domain_name != null && local.route53_zone_name != null
}

resource "aws_apigatewayv2_api" "rest_api" {
  name          = local.api_name
  protocol_type = "HTTP"
  body          = local.openapi_definition
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.rest_api.id
  name        = local.stage_name
  auto_deploy = true

  access_log_settings {
    destination_arn = null # add if CloudWatch logs desired
    format          = null # or use a structured format
  }
}

# Optional: custom domain setup
resource "aws_apigatewayv2_domain_name" "custom" {
  count = local.enable_custom_domain ? 1 : 0

  domain_name = local.domain_name

  domain_name_configuration {
    certificate_arn = module.acm_certificate.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "mapping" {
  count    = local.enable_custom_domain ? 1 : 0
  api_id   = aws_apigatewayv2_api.rest_api.id
  stage    = aws_apigatewayv2_stage.default.id
  domain_name = aws_apigatewayv2_domain_name.custom[0].id
}

data "aws_route53_zone" "zone" {
  count = local.enable_custom_domain ? 1 : 0
  name  = local.route53_zone_name
}

resource "aws_route53_record" "custom_domain" {
  count   = local.enable_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.zone[0].zone_id
  name    = local.domain_name
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.custom[0].domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.custom[0].domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

# Optional: grant permission for each Lambda to be invoked by the API Gateway
resource "aws_lambda_permission" "api" {
  for_each = local.lambda_integrations

  statement_id  = "AllowExecutionFromApiGateway-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.rest_api.execution_arn}/*/*"
}

# SSM output
resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    api_id           = aws_apigatewayv2_api.rest_api.id,
    api_endpoint     = aws_apigatewayv2_api.rest_api.api_endpoint,
    stage_name       = local.stage_name,
    custom_domain    = local.enable_custom_domain ? local.domain_name : null
  })
}
