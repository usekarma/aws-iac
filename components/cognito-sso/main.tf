locals {
  user_pool_name = try(local.config.user_pool_name, "cognito-${var.nickname}-pool")
  client_name    = try(local.config.client_name, "cognito-${var.nickname}-client")
  domain_prefix  = try(local.config.domain_prefix, "cognito-${var.nickname}")

  # REQUIRED: callback_hosts must come from config
  # e.g. ["grafana.usekarma.dev", "prometheus.usekarma.dev", ...]
  callback_hosts = local.config.callback_hosts

  # Convert hosts → full callback URLs expected by ALB / Cognito
  callback_urls = [
    for h in local.callback_hosts :
    format("https://%s/oauth2/idpresponse", h)
  ]

  # One canonical place Cognito should send users after logout
  # (defaults to "home" of first callback host)
  logout_uri = try(
    local.config.logout_uri,
    format("https://%s/", local.callback_hosts[0]) # e.g. https://grafana.usekarma.dev/
  )

  # Cognito "Allowed sign-out URLs" – keep this in sync with logout_uri
  logout_urls = try(
    local.config.logout_urls,
    [local.logout_uri]
  )
}

data "aws_region" "current" {}

resource "aws_cognito_user_pool" "this" {
  name = local.user_pool_name

  # Simple, sensible defaults (override via config if needed)
  password_policy {
    minimum_length    = try(local.config.password_min_length, 8)
    require_lowercase = try(local.config.require_lowercase, true)
    require_numbers   = try(local.config.require_numbers, true)
    require_symbols   = try(local.config.require_symbols, false)
    require_uppercase = try(local.config.require_uppercase, true)
  }

  auto_verified_attributes = try(local.config.auto_verified_attributes, ["email"])

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = local.tags
}

resource "aws_cognito_user_pool_client" "this" {
  name         = local.client_name
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = try(local.config.allowed_oauth_flows, ["code"])
  allowed_oauth_scopes                 = try(local.config.allowed_oauth_scopes, ["openid", "email", "profile"])
  supported_identity_providers         = try(local.config.supported_identity_providers, ["COGNITO"])

  callback_urls = local.callback_urls
  logout_urls   = local.logout_urls

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = local.domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}

# Hosted UI base URL (re-use this in runtime + ALB)
locals {
  hosted_ui_base_url = format(
    "https://%s.auth.%s.amazoncognito.com",
    aws_cognito_user_pool_domain.this.domain,
    data.aws_region.current.id
  )
}

resource "aws_ssm_parameter" "runtime" {
  name = local.runtime_path
  type = "String"
  value = jsonencode({
    user_pool_id     = aws_cognito_user_pool.this.id
    user_pool_arn    = aws_cognito_user_pool.this.arn
    client_id        = aws_cognito_user_pool_client.this.id
    user_pool_domain = aws_cognito_user_pool_domain.this.domain

    region = data.aws_region.current.id

    hosted_ui_base_url = local.hosted_ui_base_url
    logout_uri         = local.logout_uri

    # Fully baked Cognito logout URL for convenience (ALB or docs can use this)
    logout_url = format(
      "%s/logout?client_id=%s&logout_uri=%s&redirect_uri=%s",
      local.hosted_ui_base_url,
      aws_cognito_user_pool_client.this.id,
      urlencode(local.logout_uri),
      urlencode(local.logout_uri)
    )
  })

  tags = local.tags
}
