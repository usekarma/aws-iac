locals {
  # AMI metadata from SSM (JSON)
  redpanda_ami_meta = jsondecode(nonsensitive(data.aws_ssm_parameter.redpanda_ami.value))
  redpanda_ami_id   = local.redpanda_ami_meta.ami_id
  redpanda_root_gb  = try(local.redpanda_ami_meta.root_volume_gb, 30)
  redpanda_nodeexp_ver = try(local.redpanda_ami_meta.node_exporter_version, "1.8.2")

  # Instance / data volume config
  redpanda_instance_type = try(local.config.redpanda_instance_type, "c6i.large")
  redpanda_volume_gb     = try(local.config.redpanda_volume_gb, 200)
  redpanda_iops          = try(local.config.redpanda_iops, 3000)
  redpanda_throughput    = try(local.config.redpanda_throughput, 125)

  redpanda_retention = try(local.config.redpanda_retention, 7 * 24 * 60 * 60 * 1000)

  # Ports + topic
  redpanda_port          = try(local.config.redpanda_port, 9092)
  redpanda_admin_port    = try(local.config.redpanda_admin_port, 9644)
  redpanda_topic         = try(local.config.redpanda_topic, "clickhouse_ingest")
  redpanda_partitions    = try(local.config.redpanda_partitions, 3)
  redpanda_exporter_port = try(local.config.redpanda_exporter_port, 9644)
  redpanda_nodeexp_port  = try(local.config.redpanda_node_port, 9100)

  redpanda_brokers = (
    local.enable_redpanda && length(aws_instance.redpanda) > 0 ?
    "${aws_instance.redpanda[0].private_ip}:${local.redpanda_port}" :
    null
  )
}

data "aws_ssm_parameter" "redpanda_ami" {
  name = "${var.iac_prefix}/${var.component_name}/ami/redpanda"
}

# SG for Redpanda
resource "aws_security_group" "redpanda" {
  count       = local.enable_redpanda ? 1 : 0
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
  count                        = local.enable_redpanda ? 1 : 0
  security_group_id            = local.vpc_sg_id
  referenced_security_group_id = aws_security_group.redpanda[0].id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Allow HTTPS from Redpanda SG to SSM endpoints"
}

# Allow ClickHouse (and optionally Connect) to reach Redpanda 9092
resource "aws_vpc_security_group_ingress_rule" "redpanda_from_clickhouse_9092" {
  count                        = local.enable_redpanda ? 1 : 0
  security_group_id            = aws_security_group.redpanda[0].id
  referenced_security_group_id = local.vpc_sg_id
  ip_protocol                  = "tcp"
  from_port                    = local.redpanda_port
  to_port                      = local.redpanda_port
  description                  = "ClickHouse to Redpanda 9092"
}

# Admin port (9644) from ClickHouse SG (optional)
resource "aws_vpc_security_group_ingress_rule" "redpanda_admin_from_clickhouse" {
  count                        = local.enable_redpanda ? 1 : 0
  security_group_id            = aws_security_group.redpanda[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.redpanda_admin_port
  to_port                      = local.redpanda_admin_port
  description                  = "ClickHouse to Redpanda Admin 9644"
}

resource "aws_vpc_security_group_ingress_rule" "redpanda_node_exporter" {
  count                        = local.enable_redpanda ? 1 : 0
  security_group_id            = aws_security_group.redpanda[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.redpanda_nodeexp_port
  to_port                      = local.redpanda_nodeexp_port
  description                  = "ClickHouse to Redpanda Node Exporter 9100"
}

# EBS volume (data)
resource "aws_ebs_volume" "redpanda_data" {
  count             = local.enable_redpanda ? 1 : 0
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
  count                       = local.enable_redpanda ? 1 : 0
  ami                         = local.redpanda_ami_id
  instance_type               = local.redpanda_instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.id
  vpc_security_group_ids      = [aws_security_group.redpanda[0].id, local.vpc_sg_id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = local.redpanda_root_gb  # must be >= root_volume_size_gb in redpanda-ami.pkr.hcl
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  user_data_base64 = base64encode(templatefile("${path.module}/tmpl/redpanda-userdata.sh.tmpl", {
    # Leave blank to auto-detect largest non-root NVMe (Nitro-safe)
    EBS_DEVICE  = "" # e.g., "/dev/nvme1n1" to pin explicitly
    MOUNT_POINT = "/var/lib/redpanda"
    MARKER_FILE = "/var/local/BOOTSTRAP_OK"

    # Backups
    CLICKHOUSE_BUCKET = local.backup_bucket_name
    CLICKHOUSE_PREFIX = local.backup_prefix

    # Region for ClickHouse + AWS CLI (used by systemd drop-in)
    AWS_REGION = data.aws_region.current.id

    REDPANDA_PORT       = local.redpanda_port
    REDPANDA_ADMIN_PORT = local.redpanda_admin_port
    REDPANDA_BOOT_TOPIC = local.redpanda_topic
    REDPANDA_PARTITIONS = local.redpanda_partitions
    REDPANDA_RF         = 1

    NODE_EXPORTER_VERSION = local.redpanda_nodeexp_ver
  }))

  tags = merge(local.tags, {
    Name     = "${var.nickname}-redpanda"
    Nickname = var.nickname
    Role     = "redpanda"
  })
}

resource "aws_volume_attachment" "redpanda_data" {
  count       = local.enable_redpanda ? 1 : 0
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.redpanda_data[0].id
  instance_id = aws_instance.redpanda[0].id
}
