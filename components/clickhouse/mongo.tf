locals {
  mongo_enable        = try(local.config.mongo_enable, true)
  mongo_instance_type = try(local.config.mongo_instance_type, "r6i.large")
  mongo_volume_gb     = try(local.config.mongo_volume_gb, 300)
  mongo_iops          = try(local.config.mongo_iops, 3000)
  mongo_throughput    = try(local.config.mongo_throughput, 125)
  mongo_port          = try(local.config.mongo_port, 27017)

  # Which SGs may connect to Mongo? (e.g., Kafka Connect SG, ClickHouse SG)
  mongo_allowed_sg_ids = toset(try(local.config.mongo_allowed_security_group_ids, []))

  # Optional CIDR allowlist (use sparingly; prefer SG-to-SG)
  mongo_allowed_cidrs = toset(try(local.config.mongo_allowed_cidrs, []))
}

resource "aws_security_group" "mongo" {
  count       = local.mongo_enable ? 1 : 0
  name        = "${var.nickname}-sg-mongo"
  description = "MongoDB single-node RS for CDC"
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

  tags = merge(local.tags, { Role = "mongo", Name = "${var.nickname}-sg-mongo" })
}

# Allow from permitted SGs (Kafka Connect, ClickHouse if needed) on 27017
resource "aws_vpc_security_group_ingress_rule" "mongo_from_sgs_27017" {
  for_each                     = local.mongo_enable ? local.mongo_allowed_sg_ids : toset([])
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_port
  to_port                      = local.mongo_port
  description                  = "Mongo 27017 from allowed SG"
}

# Optional: allow from specific CIDRs (e.g., admin jump host)
resource "aws_vpc_security_group_ingress_rule" "mongo_from_cidrs_27017" {
  for_each          = local.mongo_enable ? local.mongo_allowed_cidrs : toset([])
  security_group_id = aws_security_group.mongo[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = local.mongo_port
  to_port           = local.mongo_port
  description       = "Mongo 27017 from allowed CIDR"
}

# Data volume for Mongo
resource "aws_ebs_volume" "mongo_data" {
  count             = local.mongo_enable ? 1 : 0
  availability_zone = data.aws_subnet.chosen.availability_zone
  size              = local.mongo_volume_gb
  type              = "gp3"
  iops              = local.mongo_iops
  throughput        = local.mongo_throughput
  encrypted         = true
  tags              = merge(local.tags, { Name = "${var.nickname}-mongo-data" })
}

# Mongo EC2 instance
resource "aws_instance" "mongo" {
  count                       = local.mongo_enable ? 1 : 0
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.mongo_instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.id
  vpc_security_group_ids      = [aws_security_group.mongo[0].id, local.vpc_sg_id]
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
    REDPANDA_BROKERS    = format("%s:%d", aws_instance.redpanda[0].private_ip, local.redpanda_port)
    REDPANDA_TOPIC      = local.redpanda_topic
    REDPANDA_PARTITIONS = local.redpanda_partitions
    REDPANDA_RETMS      = local.redpanda_retention

    # Region for ClickHouse + AWS CLI (used by systemd drop-in)
    AWS_REGION = data.aws_region.current.id
  }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-mongo"
    Nickname = var.nickname
    Role     = "mongo"
  })
}

resource "aws_volume_attachment" "mongo_data" {
  count       = local.mongo_enable ? 1 : 0
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.mongo_data[0].id
  instance_id = aws_instance.mongo[0].id
}
