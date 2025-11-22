// mongo-ami.pkr.hcl
// Builds a MongoDB base AMI on Amazon Linux 2023

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
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type    = string
  default = "m6i.large"
}

variable "root_volume_size_gb" {
  type    = number
  default = 30
}

variable "mongo_major" {
  type    = number
  default = 7
}

source "amazon-ebs" "mongo_base" {
  region                      = var.aws_region
  availability_zone           = "${var.aws_region}b" # <— ADD THIS
  instance_type               = var.instance_type
  ssh_username                = "ec2-user"
  ami_name                    = "mongo-base-${local.timestamp}"
  ami_description             = "MongoDB base AMI ${var.mongo_major}.x"
  associate_public_ip_address = true

  # Amazon Linux 2023
  source_ami_filter {
    filters = {
      name                = "al2023-ami-*-kernel-6.1-x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    owners      = ["137112412989"] # Amazon
    most_recent = true
  }

  launch_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    delete_on_termination = true
  }

  tags = {
    Name      = "mongo-base"
    Role      = "mongo"
    ManagedBy = "packer"
    OS        = "al2023"
  }
}

build {
  name    = "mongo-base"
  sources = ["source.amazon-ebs.mongo_base"]

  # AMI-safe installer (no mounts, no RS init, no restore)
  provisioner "shell" {
    script = "scripts/install-mongo.sh"
    environment_vars = [
      "MONGO_MAJOR=${var.mongo_major}"
    ]

    # run the script as root
    execute_command = "sudo -E bash '{{ .Path }}'"
  }

  # Cleanup
  provisioner "shell" {
    inline = [
      "sudo rm -rf /var/log/*",
      "sudo dnf clean all || true",
      "sudo yum clean all || true"
    ]
  }
}
