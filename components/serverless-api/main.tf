data "external" "resolved" {
  program = ["python", "${path.module}/nickname_resolver.py"]
  query = {
    iac_base  = var.iac_prefix
    component = var.component_name
    nickname  = var.nickname
  }
}

locals {
  api_name             = local.config.api_name
  lambda_integrations  = try(jsondecode(data.external.resolved.result.lambda_integrations), {})
  stage_name           = try(local.config.stage_name, "v1")
  enable_custom_domain = try(local.config.enable_custom_domain, false)
  domain_name          = try(local.config.domain_name, null)
  route53_zone_name    = try(local.config.route53_zone_name, null)
}

data "aws_route53_zone" "zone" {
  count = local.enable_custom_domain ? 1 : 0
  name  = local.route53_zone_name
}

module "acm_certificate" {
  count  = local.enable_custom_domain ? 1 : 0
  source = "git::https://github.com/usekarma/aws-modules.git//acm-certificate?ref=main"

  providers = {
    aws = aws.us_east_1
  }

  domain_name = local.domain_name
  zone_id     = data.aws_route53_zone.zone[0].zone_id
  tags        = local.tags
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = local.stage_name
  auto_deploy = true
}

resource "aws_apigatewayv2_domain_name" "custom" {
  count = local.enable_custom_domain ? 1 : 0

  domain_name = local.domain_name

  domain_name_configuration {
    certificate_arn = module.acm_certificate[0].certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "mapping" {
  count       = local.enable_custom_domain ? 1 : 0
  api_id      = aws_apigatewayv2_api.http_api.id
  stage       = aws_apigatewayv2_stage.default.id
  domain_name = aws_apigatewayv2_domain_name.custom[0].id
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

resource "aws_lambda_permission" "api" {
  for_each = local.lambda_integrations

  statement_id  = "AllowExecutionFromApiGateway-${replace(replace(each.key, " ", "_"), "/", "_")}"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"

  depends_on = [aws_apigatewayv2_api.http_api]
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = local.lambda_integrations

  api_id             = aws_apigatewayv2_api.http_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = each.value
  integration_method = "POST"
  payload_format_version = "2.0"

  timeout_milliseconds = 29000
}

resource "aws_apigatewayv2_route" "lambda" {
  for_each = local.lambda_integrations

  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.key].id}"
}

resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    api_id        = aws_apigatewayv2_api.http_api.id,
    api_endpoint  = aws_apigatewayv2_api.http_api.api_endpoint,
    stage_name    = local.stage_name,
    custom_domain = local.enable_custom_domain ? local.domain_name : null
  })

  overwrite = true
  tier      = "Standard"
}
