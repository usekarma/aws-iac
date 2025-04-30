resource "aws_s3_bucket" "s3_bucket" {
  bucket        = local.config.bucket_name
  force_destroy = try(local.config.force_destroy, true)
  tags          = local.tags
}

resource "aws_s3_bucket_versioning" "versioning" {
  bucket = aws_s3_bucket.s3_bucket.id

  versioning_configuration {
    status = try(local.config.versioning, true) ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_ownership_controls" "ownership" {
  count  = try(local.config.enforce_owner, true) ? 1 : 0
  bucket = aws_s3_bucket.s3_bucket.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "block" {
  count = try(local.config.block_public_access, true) ? 1 : 0

  bucket = aws_s3_bucket.s3_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sse" {
  count = try(local.config.enable_encryption, false) ? 1 : 0

  bucket = aws_s3_bucket.s3_bucket.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = try(local.config.sse_algorithm, "AES256")
    }
  }
}

resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    bucket_name = aws_s3_bucket.s3_bucket.bucket
  })

  overwrite = true
  tier      = "Standard"
}
