packer {
  required_version = ">= 1.9.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 1.3.0"
    }
  }
}

locals {
  timestamp            = regex_replace(timestamp(), "[- TZ:]", "")
  clickhouse_ver_label = var.clickhouse_version != "" ? var.clickhouse_version : "latest"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "base_ami_owner" {
  type = string
  # For Amazon Linux 2023, "amazon" is fine; alternatively:
  # default = "137112412989"
  default = "amazon"
}

variable "clickhouse_version" {
  type    = string
  default = ""
}

variable "prometheus_version" {
  type    = string
  default = ""
}

variable "node_exporter_version" {
  type    = string
  default = ""
}

variable "grafana_version" {
  type    = string
  default = ""
}

source "amazon-ebs" "clickhouse_base" {
  region            = var.aws_region
  profile           = "prod-iac"
  availability_zone = "us-east-1b"

  instance_type               = "t3.medium"
  ssh_username                = "ec2-user"
  ami_name                    = "clickhouse-base-${local.clickhouse_ver_label}-${local.timestamp}"
  ami_description             = "Base AMI with ClickHouse ${local.clickhouse_ver_label}"
  associate_public_ip_address = true

  # 👇 ensure root disk isn't tiny
  launch_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_size           = 30 # 30GB root; you can go 20 if you want
    volume_type           = "gp3"
    delete_on_termination = true
  }

  source_ami_filter {
    filters = {
      name                = "al2023-ami-*-x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    owners      = [var.base_ami_owner]
    most_recent = true
  }

  tags = {
    Name          = "clickhouse-base"
    Component     = "clickhouse"
    Role          = "db"
    ManagedBy     = "packer"
    ClickHouseVer = local.clickhouse_ver_label
  }
}

build {
  name    = "clickhouse-base"
  sources = ["source.amazon-ebs.clickhouse_base"]

  provisioner "shell" {
    script = "${path.root}/scripts/install-clickhouse.sh"
    env = {
      CLICKHOUSE_VERSION = var.clickhouse_version
    }
  }

  provisioner "shell" {
    script = "${path.root}/scripts/install-observability.sh"
    environment_vars = [
      "PROMETHEUS_VER=${var.prometheus_version}",
      "NODEEXP_VER=${var.node_exporter_version}",
      "GRAFANA_VER=${var.grafana_version}",
    ]
  }

}
