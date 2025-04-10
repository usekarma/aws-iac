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

variable "nickname" {
  description = "The nickname for the Route53 zone (used in Parameter Store)"
  type        = string
}

data "aws_ssm_parameter" "config" {
  name = "/iac/route53-zone/${var.nickname}/config"
}

locals {
  config        = jsondecode(data.aws_ssm_parameter.config.value)
  zone_name     = local.config.zone_name
  comment       = try(local.config.comment, "Managed by Terraform")
  tags          = try(local.config.tags, {})
  root_records  = try(local.config.root_records, {})
}

resource "aws_route53_zone" "zone" {
  name    = local.zone_name
  comment = local.comment
  tags    = local.tags
}

# Optional: MX records
resource "aws_route53_record" "mx" {
  count = contains(keys(local.root_records), "MX") ? 1 : 0

  zone_id = aws_route53_zone.zone.zone_id
  name    = local.zone_name
  type    = "MX"
  ttl     = 300
  records = local.root_records["MX"]
}

# Optional: TXT records
resource "aws_route53_record" "txt" {
  count = contains(keys(local.root_records), "TXT") ? 1 : 0

  zone_id = aws_route53_zone.zone.zone_id
  name    = local.zone_name
  type    = "TXT"
  ttl     = 300
  records = local.root_records["TXT"]
}

# Optional: Custom-named TXT records like _dmarc, etc.
resource "aws_route53_record" "txt_custom" {
  for_each = try(local.root_records.TXT_CUSTOM, {})

  zone_id = aws_route53_zone.zone.zone_id
  name    = each.key
  type    = "TXT"
  ttl     = 300
  records = [each.value]
}

# Optional: CNAME records like www -> strall.com
resource "aws_route53_record" "cname" {
  for_each = try(local.root_records.CNAME, {})

  zone_id = aws_route53_zone.zone.zone_id
  name    = each.key
  type    = "CNAME"
  ttl     = 300
  records = [each.value]
}

# Outputs
resource "aws_ssm_parameter" "runtime" {
  name  = "/iac/route53-zone/${var.nickname}/runtime"
  type  = "String"
  value = jsonencode({
    zone_id      = aws_route53_zone.zone.zone_id,
    zone_arn     = aws_route53_zone.zone.arn,
    name_servers = aws_route53_zone.zone.name_servers
  })
}
