output "cloudfront_url" {
  value = aws_cloudfront_distribution.site.domain_name
}

output "s3_website_url" {
  value = aws_s3_bucket_website_configuration.site.website_endpoint
}
