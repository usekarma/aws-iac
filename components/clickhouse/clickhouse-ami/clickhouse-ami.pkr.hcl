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
  timestamp = regex_replace(timestamp(), "[- TZ:]", "")
  ver_label = var.clickhouse_version != "" ? var.clickhouse_version : "latest"

  # Values that TF needs to stay in sync with
  root_volume_size_gb = var.root_volume_size_gb
  os_version          = "Amazon Linux 2023"
  arch                = "x86_64"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "base_ami_owner" {
  type    = string
  default = "amazon"
}

variable "root_volume_size_gb" {
  type    = number
  default = 30
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

source "amazon-ebs" "clickhouse" {
  region            = var.aws_region
  profile           = "prod-iac"
  availability_zone = "${var.aws_region}b"

  instance_type = "t3.medium"
  ssh_username  = "ec2-user"

  ami_name        = "clickhouse-base-${local.ver_label}-${local.timestamp}"
  ami_description = "ClickHouse base AMI ${local.ver_label}"

  associate_public_ip_address = true

  launch_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_size           = local.root_volume_size_gb
    volume_type           = "gp3"
    delete_on_termination = true
  }

  source_ami_filter {
    filters = {
      name                = "al2023-ami-*-x86_64"
      virtualization-type = "hvm"
      root-device-type    = "ebs"
    }
    owners      = [var.base_ami_owner]
    most_recent = true
  }

  tags = {
    Name         = "clickhouse-base"
    Component    = "clickhouse"
    ManagedBy    = "packer"
    CH_Version   = local.ver_label
    OS           = local.os_version
    Architecture = local.arch
  }
}

build {
  name    = "clickhouse-base"
  sources = ["source.amazon-ebs.clickhouse"]

  # ClickHouse install
  provisioner "shell" {
    script = "${path.root}/scripts/install-clickhouse.sh"
    environment_vars = [
      "CLICKHOUSE_VERSION=${var.clickhouse_version}"
    ]
  }

  # Observability stack
  provisioner "shell" {
    script = "${path.root}/scripts/install-observability.sh"
    environment_vars = [
      "PROMETHEUS_VER=${var.prometheus_version}",
      "NODEEXP_VER=${var.node_exporter_version}",
      "GRAFANA_VER=${var.grafana_version}",
    ]
  }
}
