terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "functions" {
  description = "Desired declarations; roles, names, network and wiring are infrastructure-owned."
  nullable    = false
  type = map(object({
    runtime            = string
    handler            = string
    memory_size        = number
    timeout            = number
    log_retention_days = number
    environment        = optional(map(string), {})
    artifact = object({
      s3_bucket         = string
      s3_key            = string
      s3_object_version = string
      source_code_hash  = string
    })
  }))

  validation {
    condition = length(var.functions) > 0 && alltrue([for f in values(var.functions) :
      f.memory_size >= 128 && f.memory_size <= 10240 && floor(f.memory_size) == f.memory_size &&
      f.timeout >= 1 && f.timeout <= 900 && floor(f.timeout) == f.timeout &&
      contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], f.log_retention_days) &&
      can(regex("^[a-z][a-z0-9.]+$", f.runtime)) && can(regex("^[A-Za-z_][A-Za-z0-9_.]*$", f.handler)) &&
      can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", f.artifact.s3_bucket)) &&
      endswith(f.artifact.s3_key, ".zip") && basename(f.artifact.s3_key) != "empty.zip" &&
      length(trimspace(f.artifact.s3_object_version)) > 0 && !contains(["null", "latest"], f.artifact.s3_object_version) &&
      can(regex("^[A-Za-z0-9+/]{43}=$", f.artifact.source_code_hash))
    ])
    error_message = "Lambda declarations require valid sizing/log retention and an explicit versioned S3 ZIP with base64 SHA256; placeholder artifacts are forbidden."
  }
}

variable "bindings" {
  type = map(object({
    function_name = string
    role_arn      = string
    environment   = optional(map(string), {})
    vpc = optional(object({
      subnet_ids         = list(string)
      security_group_ids = list(string)
    }))
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = var.functions
  name              = "/aws/lambda/${var.bindings[each.key].function_name}"
  retention_in_days = each.value.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "this" {
  for_each          = var.functions
  function_name     = var.bindings[each.key].function_name
  role              = var.bindings[each.key].role_arn
  runtime           = each.value.runtime
  handler           = each.value.handler
  memory_size       = each.value.memory_size
  timeout           = each.value.timeout
  s3_bucket         = each.value.artifact.s3_bucket
  s3_key            = each.value.artifact.s3_key
  s3_object_version = each.value.artifact.s3_object_version
  source_code_hash  = each.value.artifact.source_code_hash

  environment {
    # Infrastructure wiring wins; config cannot override table/identity/trust fields.
    variables = merge(each.value.environment, var.bindings[each.key].environment)
  }

  dynamic "vpc_config" {
    for_each = var.bindings[each.key].vpc == null ? [] : [var.bindings[each.key].vpc]
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.this]
}

output "functions" {
  value = { for name, function in aws_lambda_function.this : name => {
    arn           = function.arn
    function_name = function.function_name
    invoke_arn    = function.invoke_arn
    artifact      = var.functions[name].artifact
  } }
}
