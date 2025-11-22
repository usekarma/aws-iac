###############################################
# MONGO – AMI Metadata, Locals, Resources
###############################################

locals {
  #
  # === Mongo AMI metadata (from SSM) ===
  #
  # Expected SSM JSON:
  # {
  #   "ami_id": "ami-xxxx",
  #   "root_volume_gb": 30,
  #   "mongo_major": "7",
  #   "mongo_exporter_version": "0.40.0",
  #   "node_exporter_version": "1.8.2"
  # }
  #
  mongo_meta = jsondecode(data.aws_ssm_parameter.mongo_ami.value)

  # Safe lookups with sane defaults so partial SSM values don't explode
  mongo_ami_id  = lookup(local.mongo_meta, "ami_id", "")
  mongo_root_gb = lookup(local.mongo_meta, "root_volume_gb", 30)

  # Allow config overrides, but fall back to SSM JSON, then hard defaults
  mongo_major = try(
    local.config.mongo_major,
    lookup(local.mongo_meta, "mongo_major", "7")
  )

  mongo_exporter_ver = try(
    local.config.mongo_exporter_ver,
    lookup(local.mongo_meta, "mongo_exporter_version", "0.40.0")
  )

  mongo_nodeexp_ver = try(
    local.config.mongo_nodeexp_ver,
    lookup(local.mongo_meta, "node_exporter_version", "1.8.2")
  )

  #
  # Instance sizing (runtime)
  #
  mongo_instance_type = try(local.config.mongo_instance_type, "r6i.large")
  mongo_volume_gb     = try(local.config.mongo_volume_gb, 300)
  mongo_iops          = try(local.config.mongo_iops, 3000)
  mongo_throughput    = try(local.config.mongo_throughput, 125)

  #
  # Ports & ReplicaSet
  #
  mongo_port          = try(local.config.mongo_port, 27017)
  mongo_rs_name       = try(local.config.mongo_rs_name, "rs0")
  mongo_exporter_port = try(local.config.mongo_exporter_port, 9216)
  mongo_nodeexp_port  = try(local.config.mongo_node_port, 9100)

  #
  # Dynamic connection string (only once IP exists)
  #
  mongo_connection_string = local.enable_mongo ? format(
    "mongodb://%s:%d/?replicaSet=%s",
    aws_instance.mongo[0].private_ip,
    local.mongo_port,
    local.mongo_rs_name
  ) : ""

  #
  # SG Allow Rules
  #
  mongo_base_sg_map = merge(
    { clickhouse = aws_security_group.clickhouse.id },
    local.enable_kconnect ? { kconnect = aws_security_group.kconnect[0].id } : {}
  )

  mongo_extra_sg_map = {
    for sg_id in try(local.config.mongo_allowed_security_group_ids, []) :
    sg_id => sg_id
  }

  mongo_allowed_sg_map = merge(
    local.mongo_base_sg_map,
    local.mongo_extra_sg_map
  )

  mongo_allowed_cidrs = toset(try(local.config.mongo_allowed_cidrs, []))
}
# AMI metadata from SSM
data "aws_ssm_parameter" "mongo_ami" {
  name = "${var.iac_prefix}/${var.component_name}/ami/mongo"
}

###################################################
# SECURITY GROUPS
###################################################

resource "aws_security_group" "mongo" {
  count       = local.enable_mongo ? 1 : 0
  name        = "${var.nickname}-sg-mongo"
  description = "MongoDB single-node RS"
  vpc_id      = local.vpc_id

  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "all egress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    ipv6_cidr_blocks = null
    prefix_list_ids  = null
    security_groups  = null
    self             = null
  }]

  tags = merge(local.tags, { Role = "mongo", Name = "${var.nickname}-sg-mongo" })
}

resource "aws_vpc_security_group_ingress_rule" "mongo_from_sgs_27017" {
  for_each                     = local.enable_mongo ? local.mongo_allowed_sg_map : {}
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_port
  to_port                      = local.mongo_port
  description                  = "Mongo from SG ${each.key}"
}

resource "aws_vpc_security_group_ingress_rule" "mongo_from_cidrs_27017" {
  for_each          = local.enable_mongo ? local.mongo_allowed_cidrs : toset([])
  security_group_id = aws_security_group.mongo[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = local.mongo_port
  to_port           = local.mongo_port
  description       = "Mongo from CIDR"
}

resource "aws_vpc_security_group_ingress_rule" "mongo_node_exporter" {
  count                        = local.enable_mongo ? 1 : 0
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_nodeexp_port
  to_port                      = local.mongo_nodeexp_port
  description                  = "Node Exporter 9100"
}

resource "aws_vpc_security_group_ingress_rule" "mongo_exporter" {
  count                        = local.enable_mongo ? 1 : 0
  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = aws_security_group.clickhouse.id
  ip_protocol                  = "tcp"
  from_port                    = local.mongo_exporter_port
  to_port                      = local.mongo_exporter_port
  description                  = "Mongo Exporter 9216"
}

###################################################
# EBS VOLUME (DATA)
###################################################

resource "aws_ebs_volume" "mongo_data" {
  count             = local.enable_mongo ? 1 : 0
  availability_zone = data.aws_subnet.chosen.availability_zone
  size              = local.mongo_volume_gb
  type              = "gp3"
  iops              = local.mongo_iops
  throughput        = local.mongo_throughput
  encrypted         = true

  tags = merge(local.tags, { Name = "${var.nickname}-mongo-data" })
}

###################################################
# EC2 INSTANCE
###################################################

resource "aws_instance" "mongo" {
  count                       = local.enable_mongo ? 1 : 0
  ami                         = local.mongo_ami_id
  instance_type               = local.mongo_instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.id
  vpc_security_group_ids      = [aws_security_group.mongo[0].id, local.vpc_sg_id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = local.mongo_root_gb   # from SSM metadata
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  user_data_base64 = base64encode(templatefile("${path.module}/tmpl/mongo-userdata.sh.tmpl", {
    EBS_DEVICE  = ""
    MOUNT_POINT = "/var/lib/mongo"
    MARKER_FILE = "/var/local/BOOTSTRAP_OK"

    CLICKHOUSE_BUCKET = local.backup_bucket_name
    CLICKHOUSE_PREFIX = local.backup_prefix
    AWS_REGION        = data.aws_region.current.id

    MONGO_PORT               = local.mongo_port
    MONGO_MAJOR              = local.mongo_major
    RS_NAME                  = local.mongo_rs_name
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
  count       = local.enable_mongo ? 1 : 0
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.mongo_data[0].id
  instance_id = aws_instance.mongo[0].id
}

###################################################
# SCHEMA BOOTSTRAP SCRIPTS
###################################################

resource "aws_s3_object" "init_sales_db" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/schema/init-sales-db.js"
  source = "${path.module}/schema/init-sales-db.js"
  etag   = filemd5("${path.module}/schema/init-sales-db.js")
  tags   = local.tags
}

resource "aws_s3_object" "seed_sales_data" {
  bucket = local.backup_bucket_name
  key    = "${local.backup_prefix}/schema/seed-sales-data.js"
  source = "${path.module}/schema/seed-sales-data.js"
  etag   = filemd5("${path.module}/schema/seed-sales-data.js")
  tags   = local.tags
}
