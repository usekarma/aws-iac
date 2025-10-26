locals {
  # --- MSK Serverless + topic ---
  msk_enable               = try(local.config.msk_enable, true)
  msk_cluster_name         = "${var.nickname}-msk-srvless"
  msk_topic_name           = try(local.config.msk_topic_name, "clickhouse_ingest")
  msk_topic_partitions     = try(local.config.msk_topic_partitions, 3)
  msk_topic_retention_ms   = try(local.config.msk_topic_retention_ms, 604800000) # 7d
  kafka_version            = try(local.config.kafka_version, "3.7.0")
  debezium_mongodb_version = try(local.config.debezium_mongodb_version, "2.6.1.Final")
  aws_msk_iam_auth_version = try(local.config.aws_msk_iam_auth_version, "1.1.8")
}

resource "aws_security_group" "msk" {
  count       = local.msk_enable ? 1 : 0
  name        = "${var.nickname}-sg-msk-srvless"
  description = "MSK Serverless cluster SG"
  vpc_id      = local.vpc.vpc_id
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "all egress"
    from_port        = 0
    to_port          = 0
    ipv6_cidr_blocks = null
    prefix_list_ids  = null
    protocol         = "-1"
    security_groups  = null
    self             = null
  }]
  tags = merge(local.tags, { Role = "msk-serverless", Name = "${var.nickname}-sg-msk-srvless" })
}

resource "aws_vpc_security_group_ingress_rule" "msk_from_clickhouse_9098" {
  count                        = local.msk_enable ? 1 : 0
  security_group_id            = aws_security_group.msk[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = 9098
  to_port                      = 9098
  description                  = "CH-to-MSK-9098-SASL-IAM"
}

resource "aws_msk_serverless_cluster" "this" {
  count        = local.msk_enable ? 1 : 0
  cluster_name = local.msk_cluster_name

  client_authentication {
    sasl {
      iam { enabled = true }
    }
  }

  vpc_config {
    # must be at least 2 private subnets across AZs
    subnet_ids         = local.vpc.private_subnet_ids
    security_group_ids = [aws_security_group.msk[0].id]
  }

  tags = local.tags
}

locals {
  msk_bootstrap = local.msk_enable ? aws_msk_serverless_cluster.this[0].bootstrap_brokers_sasl_iam : null
  msk_arn       = local.msk_enable ? aws_msk_serverless_cluster.this[0].arn : null
}

data "aws_iam_policy_document" "msk_connect" {
  statement {
    actions   = ["kafka-cluster:Connect", "kafka:GetBootstrapBrokers"]
    resources = ["*"] # scope to aws_msk_serverless_cluster.this[0].arn if you prefer
  }
}

resource "aws_iam_policy" "msk_connect" {
  count  = local.msk_enable ? 1 : 0
  name   = "${var.nickname}-clickhouse-msk-connect"
  policy = data.aws_iam_policy_document.msk_connect.json
  tags   = local.tags
}

resource "aws_iam_role_policy_attachment" "msk_connect" {
  count      = local.msk_enable ? 1 : 0
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.msk_connect[0].arn
}
