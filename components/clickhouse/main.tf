locals {
  iac_prefix   = trim(try(local.config.iac_prefix, "/iac"), "/")
  vpc_runtime  = try(local.config.vpc_runtime_path, "/${local.iac_prefix}/vpc/${var.nickname}/runtime")

  # Runtime JSON path for THIS component
  runtime_path = try(local.runtime_path, "/${local.iac_prefix}/clickhouse/${var.nickname}/runtime")

  # Instance
  instance_type = try(local.config.instance_type, "m6i.large")
  ami_owner     = "137112412989" # Amazon Linux 2023 owner (AWS)
  key_name      = try(local.config.key_name, null) # usually null; SSM-only access

  # Storage
  ebs_size_gb   = try(local.config.ebs_size_gb, 500)
  ebs_type      = try(local.config.ebs_type, "gp3")
  ebs_iops      = try(local.config.ebs_iops, 3000)
  ebs_throughput= try(local.config.ebs_throughput, 125)

  # Networking
  assign_public_ip = false
  allowed_sg_ids   = toset(try(local.config.allowed_security_group_ids, [])) # e.g., Grafana SG
  allowed_cidrs    = toset(try(local.config.allowed_cidrs, []))              # rarely needed
  use_public_subnets = false

  # DNS (optional)
  create_dns_record = try(local.config.create_dns_record, true)
  hosted_zone_id    = try(local.config.hosted_zone_id, null)   # required if create_dns_record=true
  record_name       = try(local.config.record_name, "clickhouse.example.com.") # FQDN with trailing dot recommended

  # Backups (optional)
  create_backup_bucket = try(local.config.create_backup_bucket, false)
  backup_bucket_name   = try(local.config.backup_bucket_name, null) # if not creating one
  backup_prefix        = try(local.config.backup_prefix, "clickhouse/backups")

  # CH config
  clickhouse_version   = try(local.config.clickhouse_version, "24.8") # repo track
  ch_http_port         = try(local.config.http_port, 8123)
  ch_tcp_port          = try(local.config.tcp_port, 9000)

  vpc        = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value))
  subnet_ids = local.vpc.private_subnet_ids
}

data "aws_ssm_parameter" "vpc_runtime" {
  name = local.vpc_runtime
}

data "aws_ami" "al2023" {
  owners      = [local.ami_owner]
  most_recent = true
  filter { name = "name"; values = ["al2023-ami-*-x86_64"] }
  filter { name = "architecture"; values = ["x86_64"] }
  filter { name = "root-device-type"; values = ["ebs"] }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ec2.amazonaws.com"] }
  }
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
    sid = "S3BackupsList"
    actions   = ["s3:ListBucket"]
    resources = [
      local.create_backup_bucket ? aws_s3_bucket.backups[0].arn
                                 : "arn:aws:s3:::${local.backup_bucket_name}"
    ]
  }
  statement {
    sid = "S3BackupsRW"
    actions   = ["s3:PutObject","s3:GetObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"]
    resources = [
      local.create_backup_bucket ? "${aws_s3_bucket.backups[0].arn}/${local.backup_prefix}/*"
                                 : "arn:aws:s3:::${local.backup_bucket_name}/${local.backup_prefix}/*"
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

resource "aws_security_group" "ch" {
  name        = "${var.nickname}-sg-clickhouse"
  description = "ClickHouse EC2"
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
  tags = merge(local.tags, { Role = "clickhouse", Name = "${var.nickname}-sg-clickhouse" })
}

# Allow from permitted SGs on HTTP + (optional) TCP
resource "aws_vpc_security_group_ingress_rule" "from_sgs_http" {
  for_each                     = local.allowed_sg_ids
  security_group_id            = aws_security_group.ch.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.ch_http_port
  to_port                      = local.ch_http_port
  description                  = "HTTP from allowed SG"
}

resource "aws_vpc_security_group_ingress_rule" "from_sgs_tcp" {
  for_each                     = local.allowed_sg_ids
  security_group_id            = aws_security_group.ch.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.ch_tcp_port
  to_port                      = local.ch_tcp_port
  description                  = "TCP from allowed SG"
}

# Optional CIDR allowances (use sparingly)
resource "aws_vpc_security_group_ingress_rule" "from_cidrs_http" {
  for_each          = local.allowed_cidrs
  security_group_id = aws_security_group.ch.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = local.ch_http_port
  to_port           = local.ch_http_port
  description       = "HTTP from allowed CIDR"
}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_ami.al2023.availability_zone == null ? null : null # placeholder to avoid warnings
  # Put the volume in the first AZ’s private subnet AZ
  availability_zone = data.aws_availability_zones.available.names[0]
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
# Choose the first private subnet (simple & cheap)
locals {
  subnet_id = local.subnet_ids[0]
}

data "aws_subnet" "chosen" { id = local.subnet_id }

resource "aws_instance" "ch" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.name
  vpc_security_group_ids      = [aws_security_group.ch.id]
  key_name                    = local.key_name

  root_block_device {
    encrypted = true
    volume_type = "gp3"
    volume_size = 20
  }

  user_data = base64encode(templatefile("${path.module}/userdata.sh.tmpl", {
    EBS_DEVICE       = "/dev/xvdb"
    MOUNT_POINT      = "/var/lib/clickhouse"
    CH_HTTP_PORT     = local.ch_http_port
    CH_TCP_PORT      = local.ch_tcp_port
    BACKUP_BUCKET    = local.create_backup_bucket ? aws_s3_bucket.backups[0].bucket : local.backup_bucket_name
    BACKUP_PREFIX    = local.backup_prefix
    CH_VERSION_TRACK = local.clickhouse_version,
    MSK_BOOTSTRAP    = local.msk_bootstrap,
    MSK_TOPIC        = local.msk_topic_name,
    MSK_PARTS        = local.msk_topic_partitions,
    MSK_RETMS        = local.msk_topic_retention_ms,
  }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-clickhouse"
    Nickname = var.nickname
    Role     = "clickhouse"
  })
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.ch.id
}

############################
# S3 backup bucket (optional)
############################
resource "aws_s3_bucket" "backups" {
  count  = local.create_backup_bucket ? 1 : 0
  bucket = try(local.config.backup_bucket_name, "${var.nickname}-clickhouse-backups")
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "backups" {
  count  = local.create_backup_bucket ? 1 : 0
  bucket = aws_s3_bucket.backups[0].id
  versioning_configuration { status = "Enabled" }
}

############################
# Route53 DNS (optional)
############################
resource "aws_route53_record" "a" {
  count   = local.create_dns_record && local.hosted_zone_id != null ? 1 : 0
  zone_id = local.hosted_zone_id
  name    = local.record_name
  type    = "A"
  ttl     = 60
  records = [aws_instance.ch.private_ip]
}

resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    instance_id        = aws_instance.ch.id,
    private_ip         = aws_instance.ch.private_ip,
    security_group_id  = aws_security_group.ch.id,
    data_volume_id     = aws_ebs_volume.data.id,
    http_port          = local.ch_http_port,
    tcp_port           = local.ch_tcp_port,
    dns_record         = local.create_dns_record && local.hosted_zone_id != null ? local.record_name : null,
    backup_bucket_name = local.create_backup_bucket ? aws_s3_bucket.backups[0].bucket : local.backup_bucket_name,
    backup_prefix      = local.backup_prefix,
    vpc_id             = local.vpc.vpc_id,
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
