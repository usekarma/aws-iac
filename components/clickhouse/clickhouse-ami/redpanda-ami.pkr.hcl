packer {
  required_version = ">= 1.10.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 1.3.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "root_volume_size_gb" {
  type    = number
  default = 30
}

# -------------------------------------------------------------------
#  Source AMI: Amazon Linux 2023
# -------------------------------------------------------------------
source "amazon-ebs" "redpanda" {
  region            = var.aws_region
  profile           = "prod-iac"
  availability_zone = "${var.aws_region}b"

  instance_type = "m6i.large"
  ssh_username  = "ec2-user"

  ami_name        = "redpanda-base-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  ami_description = "Redpanda base AMI on Amazon Linux 2023"

  associate_public_ip_address = true

  # Root volume (Packer syntax – NO nested ebs{} block)
  ami_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_size           = var.root_volume_size_gb
    volume_type           = "gp3"
    delete_on_termination = true
  }

  source_ami_filter {
    most_recent = true
    owners      = ["amazon"]

    filters = {
      name                = "al2023-ami-*-x86_64"
      architecture        = "x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
  }

  tags = {
    Name      = "redpanda-base"
    Component = "redpanda"
    ManagedBy = "packer"
    OS        = "Amazon Linux 2023"
    Arch      = "x86_64"
  }
}

# -------------------------------------------------------------------
#  Build Steps
# -------------------------------------------------------------------
build {
  name    = "redpanda-base"
  sources = ["source.amazon-ebs.redpanda"]

  # ---- Install Redpanda (run as root)
  provisioner "shell" {
    script          = "scripts/install-redpanda.sh"
    execute_command = "sudo -E bash '{{ .Path }}'"
  }

  # ---- Smoke Test
  provisioner "shell" {
    inline = [
      "echo '[redpanda-ami] Smoke test starting...'",
      "sudo systemctl daemon-reload || true",
      "sudo systemctl start redpanda || true",
      "sleep 10",
      "sudo systemctl status redpanda --no-pager || true",
      "sudo systemctl stop redpanda || true",
      "echo '[redpanda-ami] Smoke test complete.'"
    ]
    execute_command = "bash '{{ .Path }}'"
  }

  # ---- Cleanup
  provisioner "shell" {
    inline = [
      "echo '[redpanda-ami] Cleaning caches...'",
      "sudo dnf clean all || true",
      "sudo rm -rf /var/cache/dnf || true",
      "sudo rm -rf /var/log/* || true",
      "echo '[redpanda-ami] Cleanup done.'"
    ]
    execute_command = "bash '{{ .Path }}'"
  }
}
