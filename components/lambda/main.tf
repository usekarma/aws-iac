locals {
  functions = try(local.config.functions, {})
}

resource "aws_iam_role" "lambda_exec" {
  for_each = local.functions

  name = "lambda-${var.nickname}-${each.key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "basic_exec" {
  for_each = local.functions

  role       = aws_iam_role.lambda_exec[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "placeholder" {
  for_each = local.functions

  function_name = each.key
  role          = aws_iam_role.lambda_exec[each.key].arn
  handler       = each.value.handler
  runtime       = each.value.runtime
  memory_size   = each.value.memory_size
  timeout       = each.value.timeout

  filename         = "${path.module}/empty.zip"
  source_code_hash = filebase64sha256("${path.module}/empty.zip")

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = local.tags
}

resource "aws_ssm_parameter" "runtime" {
  for_each = local.functions

  name  = "${var.iac_prefix}/${var.component_name}/${each.key}/runtime"
  type  = "String"
  value = jsonencode({
    function_name = aws_lambda_function.placeholder[each.key].function_name,
    placeholder   = true
  })

  overwrite = true
  tier      = "Standard"
}
