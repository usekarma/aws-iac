mock_provider "aws" {}

variables {
  functions = {
    ingest = {
      runtime            = "python3.12"
      handler            = "app.lambda_handler"
      memory_size        = 512
      timeout            = 30
      log_retention_days = 14
      environment        = { LATEST_STATE_TABLE = "untrusted-override", USER_SETTING = "synthetic" }
      artifact = {
        s3_bucket         = "synthetic-artifacts"
        s3_key            = "synthetic-revision/iot-digital-twin-ingest.zip"
        s3_object_version = "synthetic-version"
        source_code_hash  = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
      }
    }
  }
  bindings = {
    ingest = {
      function_name = "synthetic-ingest"
      role_arn      = "arn:aws:iam::000000000000:role/synthetic-test-only"
      environment   = { LATEST_STATE_TABLE = "infrastructure-table" }
    }
  }
}

run "desired_contract_and_infrastructure_wiring" {
  command = plan
  assert {
    condition     = aws_lambda_function.this["ingest"].runtime == "python3.12" && aws_lambda_function.this["ingest"].handler == "app.lambda_handler"
    error_message = "Runtime and handler must come from declaration."
  }
  assert {
    condition     = aws_lambda_function.this["ingest"].s3_object_version == "synthetic-version" && aws_lambda_function.this["ingest"].source_code_hash == var.functions.ingest.artifact.source_code_hash
    error_message = "Artifact version and digest must be pinned."
  }
  assert {
    condition     = aws_lambda_function.this["ingest"].environment[0].variables.LATEST_STATE_TABLE == "infrastructure-table" && aws_lambda_function.this["ingest"].environment[0].variables.USER_SETTING == "synthetic"
    error_message = "Infrastructure wiring must override desired environment collisions."
  }
  assert {
    condition     = aws_cloudwatch_log_group.this["ingest"].retention_in_days == 14
    error_message = "Log retention must come from declaration."
  }
}

run "reject_placeholder" {
  command = plan
  variables {
    functions = { ingest = merge(var.functions.ingest, {
      artifact = merge(var.functions.ingest.artifact, { s3_key = "empty.zip" })
    }) }
  }
  expect_failures = [var.functions]
}

run "reject_unversioned" {
  command = plan
  variables {
    functions = { ingest = merge(var.functions.ingest, {
      artifact = merge(var.functions.ingest.artifact, { s3_object_version = "null" })
    }) }
  }
  expect_failures = [var.functions]
}

run "reject_empty_declarations" {
  command = plan
  variables {
    functions = {}
  }
  expect_failures = [var.functions]
}
