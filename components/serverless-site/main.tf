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

# Fetch config from Parameter Store
data "aws_ssm_parameter" "config" {
  name = "/iac/serverless-site/${var.nickname}/config"
}

locals {
  config               = jsondecode(data.aws_ssm_parameter.config.value)
  enable_custom_domain = try(local.config.enable_custom_domain, false)
  bucket_name          = local.config.content_bucket_prefix
  tags                 = local.config.tags
}

# S3 bucket for static content
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

# Origin Access Identity
resource "aws_cloudfront_origin_access_identity" "site" {
  comment = "OAI for ${local.bucket_name}"
}

# Bucket policy allowing CloudFront read access
resource "aws_s3_bucket_policy" "allow_cloudfront_read" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.site.iam_arn
        },
        Action   = "s3:GetObject",
        Resource = "${aws_s3_bucket.site.arn}/*"
      }
    ]
  })
}

# CloudFront Function for / -> /index.html
resource "aws_cloudfront_function" "rewrite_index_html" {
  name    = "rewrite-index-html-${var.nickname}"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrite /path/ to /path/index.html"

  code = <<EOF
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri += 'index.html';
  }
  return request;
}
EOF
}

# CloudFront Distribution
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

  aliases = local.enable_custom_domain ? tolist(concat([local.config.site_name], try(local.config.domain_aliases, []))) : []

  viewer_certificate {
    cloudfront_default_certificate = local.enable_custom_domain ? false : true
    acm_certificate_arn            = local.enable_custom_domain ? local.config.acm_certificate_arn : null
    ssl_support_method             = local.enable_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.enable_custom_domain ? "TLSv1.2_2021" : null
  }
}

# Optional Route 53 zone + record
data "aws_route53_zone" "selected" {
  count = local.enable_custom_domain ? 1 : 0
  name  = local.config.route53_zone_name
}

resource "aws_route53_record" "alias" {
  count   = local.enable_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.selected[0].zone_id
  name    = local.config.site_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = "Z2FDTNDATAQYW2" # Global CloudFront zone
    evaluate_target_health = false
  }
}

# Runtime output to SSM
resource "aws_ssm_parameter" "runtime" {
  name  = "/iac/serverless-site/${var.nickname}/runtime"
  type  = "String"
  value = jsonencode({
    content_bucket_prefix          = local.bucket_name,
    cloudfront_distribution_id     = aws_cloudfront_distribution.site.id,
    cloudfront_distribution_domain = aws_cloudfront_distribution.site.domain_name
  })
}
