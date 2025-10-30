locals {
  redpanda_enable        = try(local.config.redpanda_enable, true)
  redpanda_instance_type = try(local.config.redpanda_instance_type, "c6i.large")
  redpanda_volume_gb     = try(local.config.redpanda_volume_gb, 200)
  redpanda_iops          = try(local.config.redpanda_iops, 3000)
  redpanda_throughput    = try(local.config.redpanda_throughput, 125)
  redpanda_port          = 9092
  redpanda_admin_port    = 9644
  redpanda_topic         = try(local.config.redpanda_topic, "clickhouse_ingest")
  redpanda_partitions    = try(local.config.redpanda_partitions, 3)
  redpanda_retention     = try(local.config.redpanda_retention_ms, 604800000) # 7 days
}

# SG for Redpanda
resource "aws_security_group" "redpanda" {
  count       = local.redpanda_enable ? 1 : 0
  name        = "${var.nickname}-sg-redpanda"
  description = "Redpanda broker (PLAINTEXT in VPC)"
  vpc_id      = local.vpc_id
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"],
    description      = "all egress",
    from_port        = 0,
    to_port          = 0,
    ipv6_cidr_blocks = null,
    prefix_list_ids  = null,
    protocol         = "-1",
    security_groups  = null,
    self             = null
  }]
  tags = merge(local.tags, { Role = "redpanda", Name = "${var.nickname}-sg-redpanda" })
}

# Allow HTTPS between instance SGs and default SG
resource "aws_vpc_security_group_ingress_rule" "ssm_endpoints_from_redpanda" {
  security_group_id            = local.vpc_sg_id
  referenced_security_group_id = aws_security_group.redpanda[0].id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Allow HTTPS from Redpanda SG to SSM endpoints"
}

# Allow ClickHouse (and optionally Connect) to reach Redpanda 9092
resource "aws_vpc_security_group_ingress_rule" "redpanda_from_clickhouse_9092" {
  count                        = local.redpanda_enable ? 1 : 0
  security_group_id            = aws_security_group.redpanda[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.redpanda_port
  to_port                      = local.redpanda_port
  description                  = "ClickHouse to Redpanda 9092"
}

# (Optional) allow Connect SG on 9092 if you have one
# resource "aws_vpc_security_group_ingress_rule" "redpanda_from_connect_9092" {
#   count                        = local.redpanda_enable && contains(keys(local.allowed_sg_ids), "connect") ? 1 : 0
#   security_group_id            = aws_security_group.redpanda[0].id
#   referenced_security_group_id = aws_security_group.connect.id
#   ip_protocol                  = "tcp"
#   from_port                    = local.redpanda_port
#   to_port                      = local.redpanda_port
#   description                  = "Connect to Redpanda 9092"
# }

# Admin port (9644) from ClickHouse SG (optional)
resource "aws_vpc_security_group_ingress_rule" "redpanda_admin_from_clickhouse" {
  count                        = local.redpanda_enable ? 1 : 0
  security_group_id            = aws_security_group.redpanda[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.redpanda_admin_port
  to_port                      = local.redpanda_admin_port
  description                  = "ClickHouse to Redpanda Admin 9644"
}

# EBS volume (data)
resource "aws_ebs_volume" "redpanda_data" {
  count             = local.redpanda_enable ? 1 : 0
  availability_zone = data.aws_subnet.chosen.availability_zone
  size              = local.redpanda_volume_gb
  type              = "gp3"
  iops              = local.redpanda_iops
  throughput        = local.redpanda_throughput
  encrypted         = true
  tags              = merge(local.tags, { Name = "${var.nickname}-redpanda-data" })
}

# Redpanda EC2
resource "aws_instance" "redpanda" {
  count                       = local.redpanda_enable ? 1 : 0
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.redpanda_instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.id
  vpc_security_group_ids      = [aws_security_group.redpanda[0].id, local.vpc_sg_id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 20
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  user_data_base64 = base64encode(templatefile("${path.module}/userdata.sh.tmpl", {
    # Leave blank to auto-detect largest non-root NVMe (Nitro-safe)
    EBS_DEVICE  = "" # e.g., "/dev/nvme1n1" to pin explicitly
    MOUNT_POINT = "/var/lib/clickhouse"
    MARKER_FILE = "/var/local/BOOTSTRAP_OK"

    # ClickHouse network/versions (aligns with locals)
    CLICKHOUSE_HTTP_PORT     = local.clickhouse_http_port
    CLICKHOUSE_TCP_PORT      = local.clickhouse_tcp_port
    CLICKHOUSE_VERSION_TRACK = local.clickhouse_version

    # Backups
    BACKUP_BUCKET = local.backup_bucket_name
    BACKUP_PREFIX = local.backup_prefix

    # New Redpanda vars
    REDPANDA_BROKERS    = ""
    REDPANDA_TOPIC      = local.redpanda_topic
    REDPANDA_PARTITIONS = local.redpanda_partitions
    REDPANDA_RETMS      = local.redpanda_retention

    # Region for ClickHouse + AWS CLI (used by systemd drop-in)
    AWS_REGION = data.aws_region.current.id
  }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-redpanda"
    Nickname = var.nickname
    Role     = "redpanda"
  })
}

resource "aws_volume_attachment" "redpanda_data" {
  count       = local.redpanda_enable ? 1 : 0
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.redpanda_data[0].id
  instance_id = aws_instance.redpanda[0].id
}
