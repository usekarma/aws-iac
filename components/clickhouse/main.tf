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

resource "aws_iam_role" "this" {
  name               = "${var.nickname}-clickhouse-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.this.name
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
    actions = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"]
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
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.backup.arn
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.nickname}-clickhouse-profile"
  role = aws_iam_role.this.name
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
  tags = merge(local.tags, { Role = "clickhouse", Name = "${var.nickname}-sg-clickhouse" })
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
  for_each                     = local.allowed_sg_ids
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.clickhouse_http_port
  to_port                      = local.clickhouse_http_port
  description                  = "HTTP from allowed SG"
}

resource "aws_vpc_security_group_ingress_rule" "from_sgs_tcp" {
  for_each                     = local.allowed_sg_ids
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = each.value
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
  iops              = local.ebs_type == "gp3" ? local.ebs_iops : null
  throughput        = local.ebs_type == "gp3" ? local.ebs_throughput : null
  encrypted         = true
  tags              = merge(local.tags, { Name = "${var.nickname}-clickhouse-data" })
}

############################
# EC2 instance
############################

resource "aws_instance" "clickhouse" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.name
  vpc_security_group_ids      = [aws_security_group.clickhouse.id, local.vpc_sg_id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 20
  }

  user_data_base64 = base64encode(templatefile("${path.module}/userdata.sh.tmpl", {
    EBS_DEVICE    = "" # or "/dev/nvme1n1"
    MOUNT_POINT   = "/var/lib/clickhouse"
    MARKER_FILE   = "/var/local/BOOTSTRAP_OK"
    CH_HTTP_PORT  = 8123
    CH_TCP_PORT   = 9000
    BACKUP_BUCKET = "usekarma.dev-prod" # << required
    BACKUP_PREFIX = "clickhouse"        # << required
  }))

  # user_data_base64 = base64encode(templatefile("${path.module}/userdata.sh.tmpl", {
  #   # Leave blank to auto-detect largest non-root NVMe (Nitro-safe)
  #   EBS_DEVICE   = "" # e.g., "/dev/nvme1n1" to pin explicitly
  #   MOUNT_POINT  = "/var/lib/clickhouse"
  #   MARKER_FILE  = "/var/local/BOOTSTRAP_OK"
  #   CH_HTTP_PORT = local.clickhouse_http_port
  #   CH_TCP_PORT  = local.clickhouse_tcp_port
  #   CH_VERSION_TRACK = local.clickhouse_version

  #   # MSK
  #   MSK_BOOTSTRAP = coalesce(local.msk_bootstrap, "")
  #   MSK_TOPIC     = local.msk_topic_name
  #   MSK_PARTS     = local.msk_topic_partitions
  #   MSK_RETMS     = local.msk_topic_retention_ms

  #   KAFKA_VER            = local.kafka_version,
  #   DEBEZIUM_MONGODB_VER = local.debezium_mongodb_version
  #   AWS_MSK_IAM_AUTH_VER = local.aws_msk_iam_auth_version

  # Backups
  #   BACKUP_BUCKET = local.backup_bucket_name
  #   BACKUP_PREFIX = local.backup_prefix
  # }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-clickhouse"
    Nickname = var.nickname
    Role     = "clickhouse"
  })
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.clickhouse.id
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

    # MSK
    msk_enabled            = local.msk_enable,
    msk_cluster_arn        = local.msk_arn,
    msk_bootstrap_sasl_iam = local.msk_bootstrap,
    msk_topic              = local.msk_topic_name,
    msk_topic_partitions   = local.msk_topic_partitions,
    msk_topic_retention_ms = local.msk_topic_retention_ms
  })
  overwrite = true
  tier      = "Standard"
  tags      = local.tags
}
