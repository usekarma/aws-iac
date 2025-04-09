output "content_bucket_name" {
  value = aws_s3_bucket.site.bucket
  sensitive = true
}

output "cloudfront_distribution_domain" {
  value = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}
