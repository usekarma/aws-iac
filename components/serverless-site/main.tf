provider "aws" {
  region = var.aws_region
}

locals {
  config_path  = "/iac/serverless-site/${var.nickname}/config"
  runtime_path = "/iac/serverless-site/${var.nickname}/runtime"
  config       = jsondecode(data.aws_ssm_parameter.config.value)
}

data "aws_ssm_parameter" "config" {
  name = local.config_path
}

resource "aws_s3_bucket" "site" {
  bucket = "${var.nickname}-site"
  force_destroy = true
}

resource "aws_s3_bucket_website_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "error.html"
  }
}

resource "aws_s3_bucket_public_access_block" "allow_public" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "allow_public_read" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.allow_public]
}

resource "aws_cloudfront_distribution" "site" {
  origin {
    domain_name = aws_s3_bucket_website_configuration.site.website_endpoint
    origin_id   = "s3-${aws_s3_bucket.site.bucket}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled             = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3-${aws_s3_bucket.site.bucket}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}

resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    bucket_name = aws_s3_bucket.site.bucket,
    website_url = aws_s3_bucket_website_configuration.site.website_endpoint,
    cf_domain   = aws_cloudfront_distribution.site.domain_name
  })
}
