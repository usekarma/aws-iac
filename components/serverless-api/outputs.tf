output "api_endpoint" {
  value = aws_apigatewayv2_api.rest_api.api_endpoint
}

output "custom_domain" {
  value = local.enable_custom_domain ? local.domain_name : null
}
