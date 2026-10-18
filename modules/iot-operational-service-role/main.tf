terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.69.1" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account = "623155450153"
  region  = "us-east-1"
  tags    = { Project = "iot-digital-twin", Experiment = "operational-telemetry", Environment = "sandbox" }
  regional = {
    "aws:PrincipalAccount" = local.account
    "aws:RequestedRegion"  = local.region
  }
  requested = { for k, v in local.tags : "aws:RequestTag/${k}" => v }
  owned     = { for k, v in local.tags : "aws:ResourceTag/${k}" => v }
  model_arn = "arn:aws:iotsitewise:${local.region}:${local.account}:asset-model/*"
  asset_arn = "arn:aws:iotsitewise:${local.region}:${local.account}:asset/*"
  rule_arn  = "arn:aws:iot:${local.region}:${local.account}:rule/iot_digital_twin_operational_m1"
}

resource "aws_iam_role" "cloud_control" {
  name = "iot-digital-twin-operational-m1-cloud-control"
  tags = local.tags
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "cloudformation.amazonaws.com" } }]
  })
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.account
      error_message = "M1 service role belongs only to account 623155450153."
    }
  }
}

resource "aws_iam_role_policy" "handlers" {
  name = "m1-flat-resource-handlers"
  role = aws_iam_role.cloud_control.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CreateTaggedModel", Effect = "Allow", Action = ["iotsitewise:CreateAssetModel"], Resource = "*"
        Condition = { StringEquals = merge(local.regional, local.requested) }
      },
      {
        Sid       = "CreateTaggedAsset", Effect = "Allow", Action = ["iotsitewise:CreateAsset"], Resource = local.model_arn
        Condition = { StringEquals = merge(local.regional, local.owned, local.requested) }
      },
      {
        Sid       = "OwnedModelLifecycle", Effect = "Allow", Resource = local.model_arn
        Action    = ["iotsitewise:DescribeAssetModel", "iotsitewise:ListAssetModelProperties", "iotsitewise:ListAssetModelCompositeModels", "iotsitewise:DescribeAssetModelCompositeModel", "iotsitewise:DescribeAssetModelInterfaceRelationship", "iotsitewise:ListTagsForResource", "iotsitewise:UpdateAssetModel", "iotsitewise:DeleteAssetModel"]
        Condition = { StringEquals = merge(local.regional, local.owned) }
      },
      {
        Sid       = "OwnedAssetLifecycle", Effect = "Allow", Resource = local.asset_arn
        Action    = ["iotsitewise:DescribeAsset", "iotsitewise:ListAssetProperties", "iotsitewise:ListAssociatedAssets", "iotsitewise:ListTagsForResource", "iotsitewise:UpdateAsset", "iotsitewise:UpdateAssetProperty", "iotsitewise:DeleteAsset"]
        Condition = { StringEquals = merge(local.regional, local.owned) }
      },
      {
        Sid = "PreserveOwnershipTags", Effect = "Allow", Action = ["iotsitewise:TagResource"], Resource = [local.model_arn, local.asset_arn]
        Condition = {
          StringEquals                = merge(local.regional, local.owned)
          StringEqualsIfExists        = local.requested
          "ForAllValues:StringEquals" = { "aws:TagKeys" = keys(local.tags) }
        }
      },
      {
        Sid       = "ExactRuleLifecycle", Effect = "Allow", Resource = local.rule_arn
        Action    = ["iot:CreateTopicRule", "iot:GetTopicRule", "iot:ReplaceTopicRule", "iot:DeleteTopicRule", "iot:TagResource", "iot:ListTagsForResource"]
        Condition = { StringEquals = local.regional }
      },
      {
        Sid       = "PassOnlyRoutingRole", Effect = "Allow", Action = ["iam:PassRole"]
        Resource  = "arn:aws:iam::${local.account}:role/iot-digital-twin-operational-m1-routing"
        Condition = { StringEquals = { "iam:PassedToService" = "iot.amazonaws.com", "aws:PrincipalAccount" = local.account } }
      },
      {
        # Delete stabilization reads must still reach NotFound after resource tags disappear.
        # This deliberately permits metadata reads on other assets in this account/region.
        Sid       = "AssetDeletionPolling", Effect = "Allow", Action = ["iotsitewise:DescribeAsset"]
        Resource  = local.asset_arn
        Condition = { StringEquals = local.regional }
      }
    ]
  })
}

output "service_role_arn" {
  description = "Planned output only until deployment and read-only ownership verification; never infer a live binding."
  value       = aws_iam_role.cloud_control.arn
}
output "handler_policy" { value = jsondecode(aws_iam_role_policy.handlers.policy) }
output "trust_policy" { value = jsondecode(aws_iam_role.cloud_control.assume_role_policy) }
