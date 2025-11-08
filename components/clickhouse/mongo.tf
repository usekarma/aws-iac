locals {
  mongo_enable        = try(local.config.mongo_enable, true)
  mongo_instance_type = try(local.config.mongo_instance_type, "r6i.large")
  mongo_volume_gb     = try(local.config.mongo_volume_gb, 300)
  mongo_iops          = try(local.config.mongo_iops, 3000)
  mongo_throughput    = try(local.config.mongo_throughput, 125)
  mongo_port          = try(local.config.mongo_port, 27017)
  mongo_major         = try(local.config.mongo_major, "7.0")
  mongo_rs_name       = try(local.config.mongo_rs_name, "rs0")
  mongo_exporter_ver  = try(local.config.mongo_exporter_ver, "0.40.0")
  mongo_exporter_port = try(local.config.mongo_exporter_port, 9216)
  mongo_nodeexp_ver   = try(local.config.mongo_nodeexp_ver, "1.8.2")
  mongo_nodeexp_port  = try(local.config.mongo_node_port, 9100)

  mongo_connection_string = "mongodb://${aws_instance.mongo[0].private_ip}:${local.mongo_port}/?replicaSet=rs0"

  # Which SGs may connect to Mongo? (e.g., Kafka Connect SG, ClickHouse SG)
  # Base SGs: ClickHouse + kconnect
  mongo_base_sg_map = {
    clickhouse = aws_security_group.clickhouse.id
    kconnect   = aws_security_group.kconnect.id
  }

  # Extra SGs from config (list of IDs) → turn into a map: id => id
  mongo_extra_sg_map = {
    for sg_id in try(local.config.mongo_allowed_security_group_ids, []) :
    sg_id => sg_id
  }

  # Final map of all allowed SGs
  mongo_allowed_sg_map = merge(
    local.mongo_base_sg_map,
    local.mongo_extra_sg_map
  )

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
  count                        = local.mongo_enable ? 1 : 0
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = local.vpc_sg_id
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

resource "aws_vpc_security_group_ingress_rule" "mongo_node_exporter" {
  count                        = local.mongo_enable ? 1 : 0
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_nodeexp_port
  to_port                      = local.mongo_nodeexp_port
  description                  = "ClickHouse to Mongo Node Exporter 9100"
}

resource "aws_vpc_security_group_ingress_rule" "mongo_exporter" {
  count                        = local.mongo_enable ? 1 : 0
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_exporter_port
  to_port                      = local.mongo_exporter_port
  description                  = "ClickHouse to Mongo Exporter 9216"
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

  user_data_base64 = base64encode(templatefile("${path.module}/tmpl/mongo-userdata.sh.tmpl", {
    # Leave blank to auto-detect largest non-root NVMe (Nitro-safe)
    EBS_DEVICE  = "" # e.g., "/dev/nvme1n1" to pin explicitly
    MOUNT_POINT = "/var/lib/mongo"
    MARKER_FILE = "/var/local/BOOTSTRAP_OK"

    # Backups
    BACKUP_BUCKET = local.backup_bucket_name
    BACKUP_PREFIX = local.backup_prefix

    # Region for ClickHouse + AWS CLI (used by systemd drop-in)
    AWS_REGION = data.aws_region.current.id

    MONGO_PORT  = local.mongo_port
    MONGO_MAJOR = local.mongo_major
    RS_NAME     = local.mongo_rs_name

    MONGODB_EXPORTER_VERSION = local.mongo_exporter_ver
    NODE_EXPORTER_VERSION    = local.mongo_nodeexp_ver
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
