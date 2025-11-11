locals {
  # Instance
  instance_type = try(local.config.instance_type, "m6i.large")
  ami_owner     = "137112412989"                   # Amazon Linux 2023 owner (AWS)
  key_name      = try(local.config.key_name, null) # usually null; SSM-only access

  # Storage
  ebs_size_gb    = try(local.config.ebs_size_gb, 500)
  ebs_type       = try(local.config.ebs_type, "gp3")
  ebs_iops       = try(local.config.ebs_iops, 3000)
  ebs_throughput = try(local.config.ebs_throughput, 125)

  # Networking
  assign_public_ip   = false
  allowed_sg_ids     = toset(try(local.config.allowed_security_group_ids, [])) # e.g., Grafana SG
  allowed_cidrs      = toset(try(local.config.allowed_cidrs, []))              # rarely needed
  use_public_subnets = false

  # Backups
  backup_bucket_cfg  = jsondecode(nonsensitive(data.aws_ssm_parameter.s3_bucket.value))
  backup_bucket_name = local.backup_bucket_cfg.bucket_name
  backup_prefix      = local.config.s3_bucket_prefix

  # ClickHouse config
  clickhouse_version   = try(local.config.clickhouse_version, "24.8") # repo track
  clickhouse_http_port = try(local.config.http_port, 8123)
  clickhouse_tcp_port  = try(local.config.tcp_port, 9000)

  # Grafana
  grafana_url   = try(local.config.grafana_url, "http://127.0.0.1:3000")
  grafana_admin = try(local.config.grafana_admin, "admin")
  grafana_pass  = try(local.config.grafana_pass, "admin")

  # Prometheus
  prometheus_url     = try(local.config.prometheus_url, "http://127.0.0.1:9090")
  prometheus_ds_name = try(local.config.prometheus_ds_name, "Prometheus")

  ch_only = try(local.config.clickhouse_only, false)

  # Derived feature flags (align with alb.tf / kconnect.tf)
  enable_mongo    = local.ch_only ? false : try(local.config.enable_mongo, true)
  enable_redpanda = local.ch_only ? false : try(local.config.enable_redpanda, true)
  enable_kconnect = local.ch_only ? false : try(local.config.enable_kconnect, true)

  vpc       = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value))
  vpc_id    = local.vpc.vpc_id
  vpc_sg_id = local.vpc.default_sg_id
  subnet_id = local.vpc.private_subnet_ids[0]
}

data "aws_ssm_parameter" "vpc_runtime" {
  name = "${var.iac_prefix}/vpc/${local.config.vpc_nickname}/runtime"
}

data "aws_ssm_parameter" "s3_bucket" {
  name = "${var.iac_prefix}/s3-bucket/${local.config.s3_bucket_nickname}/runtime"
}

data "aws_ami" "al2023" {
  owners      = [local.ami_owner]
  most_recent = true

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_subnet" "chosen" {
  id = local.subnet_id
}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "this" {
  name               = "${var.nickname}-clickhouse-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.this.id
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# S3 backup (scoped) policy
data "aws_iam_policy_document" "backup" {
  statement {
    sid     = "S3BackupsList"
    actions = ["s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${local.backup_bucket_name}"
    ]
  }
  statement {
    sid     = "S3BackupsRW"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts"
    ]
    resources = [
      "arn:aws:s3:::${local.backup_bucket_name}/${local.backup_prefix}/*"
    ]
  }
}

resource "aws_iam_policy" "backup" {
  name   = "${var.nickname}-clickhouse-backup"
  policy = data.aws_iam_policy_document.backup.json
  tags   = local.tags
}

resource "aws_iam_role_policy_attachment" "backup_attach" {
  role       = aws_iam_role.this.id
  policy_arn = aws_iam_policy.backup.arn
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.nickname}-clickhouse-profile"
  role = aws_iam_role.this.id
}

resource "aws_security_group" "clickhouse" {
  name        = "${var.nickname}-sg-clickhouse"
  description = "ClickHouse EC2"
  vpc_id      = local.vpc_id

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

  tags = merge(local.tags, {
    Role = "clickhouse"
    Name = "${var.nickname}-sg-clickhouse"
  })
}

# Allow HTTPS between instance SGs and default SG
resource "aws_vpc_security_group_ingress_rule" "ssm_endpoints_from_clickhouse" {
  security_group_id            = local.vpc_sg_id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Allow HTTPS from ClickHouse SG to SSM endpoints"
}

# Allow from permitted SGs on HTTP + (optional) TCP
resource "aws_vpc_security_group_ingress_rule" "from_sgs_http" {
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = local.vpc_sg_id
  ip_protocol                  = "tcp"
  from_port                    = local.clickhouse_http_port
  to_port                      = local.clickhouse_http_port
  description                  = "HTTP from allowed SG"
}

resource "aws_vpc_security_group_ingress_rule" "from_sgs_tcp" {
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = local.vpc_sg_id
  ip_protocol                  = "tcp"
  from_port                    = local.clickhouse_tcp_port
  to_port                      = local.clickhouse_tcp_port
  description                  = "TCP from allowed SG"
}

# Optional CIDR allowances (use sparingly)
resource "aws_vpc_security_group_ingress_rule" "from_cidrs_http" {
  for_each          = local.allowed_cidrs
  security_group_id = aws_security_group.clickhouse.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = local.clickhouse_http_port
  to_port           = local.clickhouse_http_port
  description       = "HTTP from allowed CIDR"
}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.chosen.availability_zone
  size              = local.ebs_size_gb
  type              = local.ebs_type
  iops              = local.ebs_type == "gp3" ? local.ebs_iops       : null
  throughput        = local.ebs_type == "gp3" ? local.ebs_throughput : null
  encrypted         = true

  tags = merge(local.tags, {
    Name = "${var.nickname}-clickhouse-data"
  })
}

############################
# EC2 instance
############################

resource "aws_instance" "clickhouse" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.id
  vpc_security_group_ids      = [aws_security_group.clickhouse.id, local.vpc_sg_id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 20
  }

  metadata_options {
    http_tokens                 = "required" # enforce IMDSv2
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
  }

  user_data_base64 = base64encode(templatefile("${path.module}/tmpl/userdata.sh.tmpl", {
    # Leave blank to auto-detect largest non-root NVMe (Nitro-safe)
    EBS_DEVICE  = "" # e.g., "/dev/nvme1n1" to pin explicitly
    MOUNT_POINT = "/var/lib/clickhouse"
    MARKER_FILE = "/var/local/BOOTSTRAP_OK"

    # ClickHouse network/versions (aligns with locals)
    CLICKHOUSE_HTTP_PORT     = local.clickhouse_http_port
    CLICKHOUSE_TCP_PORT      = local.clickhouse_tcp_port
    CLICKHOUSE_VERSION_TRACK = local.clickhouse_version

    # Backups
    CLICKHOUSE_BUCKET = local.backup_bucket_name
    CLICKHOUSE_PREFIX = local.backup_prefix

    PROMETHEUS_VER = local.prometheus_ver
    NODEEXP_VER    = local.nodeexp_ver

    # Mongo (optional – empty/zero in ClickHouse-only mode)
    MONGO_HOST      = local.enable_mongo ? aws_instance.mongo[0].private_ip : ""
    MONGO_EXP_PORT  = local.enable_mongo ? local.mongo_exporter_port        : 0
    MONGO_NODE_PORT = local.enable_mongo ? local.mongo_nodeexp_port        : 0

    # Redpanda (optional)
    REDPANDA_HOST       = local.enable_redpanda ? aws_instance.redpanda[0].private_ip                       : ""
    REDPANDA_EXP_PORT   = local.enable_redpanda ? local.redpanda_exporter_port                              : 0
    REDPANDA_NODE_PORT  = local.enable_redpanda ? local.redpanda_nodeexp_port                               : 0
    REDPANDA_BROKERS    = local.enable_redpanda ? format("%s:%d", aws_instance.redpanda[0].private_ip, local.redpanda_port) : ""
    REDPANDA_TOPIC      = local.enable_redpanda ? local.redpanda_topic                                      : ""
    REDPANDA_PARTITIONS = local.enable_redpanda ? local.redpanda_partitions                                 : 0
    REDPANDA_RETMS      = local.enable_redpanda ? local.redpanda_retention                                  : 0

    # Connector / Mongo connection (optional)
    MONGO_CONNECTION_STRING = local.enable_mongo    ? local.mongo_connection_string : ""
    KCONNECT_HOST           = local.enable_kconnect ? local.kconnect_rest_host      : ""

    GRAFANA_DASHBOARD_KEY = "${local.backup_prefix}/dashboards/mongo-clickhouse-sales-orders.json"

    # Region for ClickHouse + AWS CLI (used by systemd drop-in)
    AWS_REGION = data.aws_region.current.id
  }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-clickhouse"
    Nickname = var.nickname
    Role     = "clickhouse"
  })

  # Static list; it's okay to depend on resources that might have count=0
  depends_on = [
    aws_s3_object.prometheus_grafana_bootstrap,
    aws_s3_object.kconnect_mongo_bootstrap,
    aws_s3_object.kafka_clickhouse_bootstrap,
    aws_s3_object.grafana_bootstrap,
    aws_s3_object.sales_dashboard,
    aws_instance.mongo,
    aws_instance.redpanda,
    aws_ecs_service.kconnect,
  ]
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.clickhouse.id
}

resource "aws_s3_object" "prometheus_grafana_bootstrap" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/scripts/prometheus-grafana-bootstrap.sh"
  source = "${path.module}/scripts/prometheus-grafana-bootstrap.sh"
  etag   = filemd5("${path.module}/scripts/prometheus-grafana-bootstrap.sh")
  tags   = local.tags
}

resource "aws_s3_object" "kconnect_mongo_bootstrap" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/scripts/kconnect-mongo-bootstrap.sh"
  source = "${path.module}/scripts/kconnect-mongo-bootstrap.sh"
  etag   = filemd5("${path.module}/scripts/kconnect-mongo-bootstrap.sh")
  tags   = local.tags
}

resource "aws_s3_object" "kafka_clickhouse_bootstrap" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/scripts/kafka-clickhouse-bootstrap.sh"
  source = "${path.module}/scripts/kafka-clickhouse-bootstrap.sh"
  etag   = filemd5("${path.module}/scripts/kafka-clickhouse-bootstrap.sh")
  tags   = local.tags
}

resource "aws_s3_object" "clickhouse_schema_views" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/scripts/clickhouse-schema-views.sh"
  source = "${path.module}/scripts/clickhouse-schema-views.sh"
  etag   = filemd5("${path.module}/scripts/clickhouse-schema-views.sh")
  tags   = local.tags
}

resource "aws_s3_object" "grafana_bootstrap" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/scripts/grafana-bootstrap.sh"
  source = "${path.module}/scripts/grafana-bootstrap.sh"
  etag   = filemd5("${path.module}/scripts/grafana-bootstrap.sh")
  tags   = local.tags
}

resource "aws_s3_object" "sales_dashboard" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/dashboards/mongo-clickhouse-sales-orders.json"
  source = "${path.module}/dashboards/mongo-clickhouse-sales-orders.json"
  etag   = filemd5("${path.module}/dashboards/mongo-clickhouse-sales-orders.json")
  tags   = local.tags
}

resource "aws_ssm_parameter" "runtime" {
  name = local.runtime_path
  type = "String"

  value = jsonencode({
    instance_id        = aws_instance.clickhouse.id,
    private_ip         = aws_instance.clickhouse.private_ip,
    security_group_id  = aws_security_group.clickhouse.id,
    data_volume_id     = aws_ebs_volume.data.id,
    http_port          = local.clickhouse_http_port,
    tcp_port           = local.clickhouse_tcp_port,
    backup_bucket_name = local.backup_bucket_name,
    backup_prefix      = local.backup_prefix,
    vpc_id             = local.vpc_id,
    subnet_id          = local.subnet_id,

    # Redpanda (nulls when disabled)
    redpanda_instance_id       = local.enable_redpanda ? aws_instance.redpanda[0].id         : null,
    redpanda_private_ip        = local.enable_redpanda ? aws_instance.redpanda[0].private_ip : null,
    redpanda_security_group_id = local.enable_redpanda ? aws_security_group.redpanda[0].id   : null,
    redpanda_brokers           = local.enable_redpanda ? "${aws_instance.redpanda[0].private_ip}:${local.redpanda_port}" : null,

    # MongoDB (nulls when disabled)
    mongo_instance_id       = local.enable_mongo ? aws_instance.mongo[0].id         : null,
    mongo_private_ip        = local.enable_mongo ? aws_instance.mongo[0].private_ip : null,
    mongo_port              = local.enable_mongo ? local.mongo_port                 : null,
    mongo_replset           = local.enable_mongo ? "rs0"                            : null,
    mongo_rs_uri            = local.enable_mongo ? "mongodb://${aws_instance.mongo[0].private_ip}:${local.mongo_port}/?replicaSet=rs0" : null,
    mongo_security_group_id = local.enable_mongo ? aws_security_group.mongo[0].id   : null
  })

  overwrite = true
  tier      = "Standard"
  tags      = local.tags
}
