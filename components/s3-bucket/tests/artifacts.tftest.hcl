mock_provider "aws" {}

variables {
  component_name = "s3-bucket"
  nickname       = "artifacts"
  plan_config_json = jsonencode({
    bucket_name         = "synthetic-prototype-artifacts"
    versioning          = true
    force_destroy       = false
    enforce_owner       = true
    enable_encryption   = true
    sse_algorithm       = "AES256"
    block_public_access = true
    tags                = { Environment = "dev", Project = "iot-digital-twin", Owner = "strall" }
  })
}

run "private_versioned_artifacts" {
  command = plan

  assert {
    condition     = length(data.aws_ssm_parameter.config) == 0
    error_message = "An unpublished proposal must not read SSM config."
  }
  assert {
    condition     = !aws_s3_bucket.s3_bucket.force_destroy && aws_s3_bucket_versioning.versioning.versioning_configuration[0].status == "Enabled"
    error_message = "Artifact versions must be retained, with destructive deletion disabled."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.sse[0].rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "Artifact encryption must be enabled."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.block[0].block_public_acls && aws_s3_bucket_public_access_block.block[0].block_public_policy && aws_s3_bucket_public_access_block.block[0].ignore_public_acls && aws_s3_bucket_public_access_block.block[0].restrict_public_buckets
    error_message = "All public access controls must be enabled."
  }
  assert {
    condition     = aws_s3_bucket_ownership_controls.ownership[0].rule[0].object_ownership == "BucketOwnerEnforced" && aws_s3_bucket.s3_bucket.tags.Component == "s3-bucket"
    error_message = "Ownership and repository tags must be preserved."
  }
}

run "existing_ssm_configuration" {
  command = plan
  variables {
    plan_config_json = null
  }
  override_data {
    target = data.aws_ssm_parameter.config[0]
    values = {
      value = "{\"bucket_name\":\"synthetic-existing-bucket\",\"enable_encryption\":true}"
    }
  }
  assert {
    condition     = length(data.aws_ssm_parameter.config) == 1 && aws_s3_bucket.s3_bucket.bucket == "synthetic-existing-bucket"
    error_message = "Existing callers must continue reading SSM configuration."
  }
}
