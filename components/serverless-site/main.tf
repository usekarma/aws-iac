provider "aws" {
  region = "us-east-1"
}

data "aws_ssm_parameter" "config" {
  name = "/iac/serverless-site/strall-com/config"
}

locals {
  config      = jsondecode(data.aws_ssm_parameter.config.value)
  bucket_name = local.config.content_bucket_prefix
  tags        = local.config.tags
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

resource "aws_cloudfront_function" "rewrite_index_html" {
  name    = "rewrite-index-html"
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

  viewer_certificate {
    cloudfront_default_certificate = true
    # acm_certificate_arn            = local.config.acm_certificate_arn
    # ssl_support_method             = "sni-only"
    # minimum_protocol_version       = "TLSv1.2_2021"
  }
}

resource "aws_ssm_parameter" "runtime" {
  name  = "/iac/serverless-site/strall-com/runtime"
  type  = "String"
  value = jsonencode({
    content_bucket_prefix          = local.bucket_name,
    cloudfront_distribution_id     = aws_cloudfront_distribution.site.id,
    cloudfront_distribution_domain = aws_cloudfront_distribution.site.domain_name
  })
}
