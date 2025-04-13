terraform {
  # 🚨 DO NOT MODIFY THIS BACKEND BLOCK!
  # This empty backend block is required for compatibility with Terragrunt.
  # Terragrunt dynamically injects the actual S3/DynamoDB configuration.
  # Any changes here will be ignored — and could break Terragrunt compatibility.

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

data "aws_ssm_parameter" "config" {
  name = "/iac/serverless-site/${var.nickname}/config"
}

data "aws_route53_zone" "zone" {
  count = local.enable_custom_domain && local.zone_name != null ? 1 : 0
  name  = local.zone_name
}

locals {
  config               = jsondecode(data.aws_ssm_parameter.config.value)
  enable_custom_domain = try(local.config.enable_custom_domain, false)
  bucket_name          = local.config.content_bucket_prefix
  tags                 = local.config.tags
  domain_aliases       = try(local.config.domain_aliases, [])
  site_name            = try(local.config.site_name, null)
  zone_name            = try(local.config.route53_zone_name, null)

  enable_custom_domain_desensitized = try(nonsensitive(local.enable_custom_domain), false)
  site_name_desensitized            = try(nonsensitive(local.site_name), "")
  domain_aliases_desensitized       = try(nonsensitive(local.domain_aliases), [])
  zone_name_desensitized            = try(nonsensitive(local.zone_name), "")

  a_alias_map = local.enable_custom_domain_desensitized && local.zone_name_desensitized != "" ? {
    for domain in distinct(concat([local.site_name_desensitized], local.domain_aliases_desensitized)) :
    domain => domain
  } : {}
}

resource "aws_s3_bucket" "site" {
  bucket = local.bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "block_public" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_identity" "site" {
  comment = "OAI for ${local.bucket_name}"
}

resource "aws_s3_bucket_policy" "allow_cloudfront_read" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { AWS = aws_cloudfront_origin_access_identity.site.iam_arn },
        Action    = "s3:GetObject",
        Resource  = "${aws_s3_bucket.site.arn}/*"
      }
    ]
  })
}

resource "aws_cloudfront_function" "rewrite_index_html" {
  name    = "rewrite-index-html-${var.nickname}"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrite /path/ to /path/index.html"

  code = <<EOF
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // Redirect /about → /about/
  if (!uri.endsWith('/') && !uri.includes('.')) {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: {
        "location": { "value": uri + "/" }
      }
    };
  }

  // Rewrite /about/ → /about/index.html
  if (uri.endsWith('/')) {
    request.uri += 'index.html';
  }

  return request;
}
EOF
}

module "acm_certificate" {
  source = "git::https://github.com/tstrall/aws-modules.git//acm-certificate?ref=main"

  providers = {
    aws = aws.us_east_1
  }

  domain_name               = local.site_name
  subject_alternative_names = local.domain_aliases
  zone_id                   = data.aws_route53_zone.zone[0].zone_id
  tags                      = local.tags
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = local.config.cloudfront_comment
  tags                = local.tags

  origin {
    domain_name = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id   = "s3-${local.bucket_name}"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.site.cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3-${local.bucket_name}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.rewrite_index_html.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  aliases = local.enable_custom_domain ? tolist(concat([local.site_name], local.domain_aliases)) : []

  viewer_certificate {
    cloudfront_default_certificate = local.enable_custom_domain ? false : true
    acm_certificate_arn            = local.enable_custom_domain ? module.acm_certificate.certificate_arn : null
    ssl_support_method             = local.enable_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.enable_custom_domain ? "TLSv1.2_2021" : null
  }
}

resource "aws_route53_record" "a_aliases" {
  for_each = local.a_alias_map

  zone_id = module.acm_certificate.zone_id
  name    = each.key
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = "Z2FDTNDATAQYW2"
    evaluate_target_health = false
  }
}

resource "aws_ssm_parameter" "runtime" {
  name  = "/iac/serverless-site/${var.nickname}/runtime"
  type  = "String"
  value = jsonencode({
    content_bucket_prefix          = local.bucket_name,
    cloudfront_distribution_id     = aws_cloudfront_distribution.site.id,
    cloudfront_distribution_domain = aws_cloudfront_distribution.site.domain_name,
    custom_domain                  = local.enable_custom_domain ? local.site_name : null
  })
}
