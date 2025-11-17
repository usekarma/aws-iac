# ClickHouse AMI – **Amazon Linux 2023 + Packer**

This directory builds a **reusable, production‑ready Amazon Machine Image (AMI)** with ClickHouse preinstalled on **Amazon Linux 2023**, designed for use in EC2‑based Adage/Karma deployments.

The AMI is intentionally **minimal and fast‑booting**: ClickHouse is baked in, but schema, CDC, observability, and domain‑specific configuration are applied **at runtime** via userdata and SSM‑driven bootstrap scripts.

---

## Contents

* [Overview](#overview)
* [What’s Included](#whats-included)
* [What’s Not Included](#whats-not-included)
* [Directory Structure](#directory-structure)
* [Packer Variables](#packer-variables)
* [Build Instructions](#build-instructions)
* [Publishing AMI to SSM](#publishing-ami-to-ssm)
* [Using the AMI in Terraform](#using-the-ami-in-terraform)
* [When to Rebuild](#when-to-rebuild)
* [Future Extensions](#future-extensions)

---

## Overview

This AMI provides:

* **ClickHouse Server + Client** installed and verified
* **Systemd service wiring** (enabled, starts on boot)
* **Open network bind** via `listen.xml` (VPC security groups enforce real restrictions)
* **Fast boot / no installation overhead**

It is a **base image**, designed to be combined with runtime bootstrapping (`userdata.sh`, SSM parameters, or Adage components) to configure:

* Databases, tables, materialized views
* Kafka ENGINE tables & ingestion pipelines
* CDC connectors via Debezium / Kafka Connect
* Dashboards, exporters, Prometheus, Grafana
* Backups/restore to S3

---

## What’s Included

**Operating System**

* Amazon Linux 2023
* Latest package updates
* `dnf-utils` for repo/bootstrap tooling

**ClickHouse**

* Official ClickHouse YUM repo & packages

  * `clickhouse-common-static`
  * `clickhouse-server`
  * `clickhouse-client`
* System user: `clickhouse`
* Required dirs:

  * `/etc/clickhouse-server`
  * `/var/lib/clickhouse`
  * `/var/log/clickhouse-server`
* Config fragment: `/etc/clickhouse-server/config.d/listen.xml`
* Systemd service installed + enabled

**Smoke Test during build**

```bash
systemctl start clickhouse-server
clickhouse-client -q "SELECT 1"
systemctl stop clickhouse-server
```

**Cleanup**

* Removes logs, cache, package metadata
* Results in small, fast AMI

---

## What’s Not Included (By Design)

These belong in **runtime/bootstrap scripts**, not the base AMI:

* Database schema (e.g. `sales`)
* ClickHouse Kafka ENGINE tables
* Debezium / Kafka Connect configuration
* Prometheus / Grafana / Node Exporter
* Backup restore automation
* PoC‑specific logic or config

Your existing scripts such as:

* `clickhouse-schema-views.sh`
* `kafka-clickhouse-bootstrap.sh`
* `kconnect-mongo-bootstrap.sh`
* `grafana-bootstrap.sh`

…should be run **after instance launch**, not baked in.

---

## Directory Structure

```txt
clickhouse-ami/
├── clickhouse-ami.pkr.hcl      # Main Packer build file
├── variables.pkr.hcl           # Version + region vars
├── Makefile                    # Build + publish helpers
└── scripts/
    ├── install-clickhouse.sh   # Installs ClickHouse (included)
    ├── install-observability.sh# (future)
    └── harden-base.sh          # (future)
```

---

## Packer Variables

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "base_ami_owner" {
  type    = string
  default = "137112412989" # Amazon Linux 2023 owner
}

variable "clickhouse_version" {
  type    = string
  default = "24.3.5.47"
}

variable "prometheus_version" {
  type    = string
  default = "2.53.1"
}

variable "node_exporter_version" {
  type    = string
  default = "1.8.1"
}
```

Currently used vars: `aws_region`, `clickhouse_version`. The rest are reserved for future observability AMIs.

AMI names follow:

```
clickhouse-base-${clickhouse_version}-${timestamp}
```

Example:

```
clickhouse-base-24.3.5.47-20251117002419
```

---

## Build Instructions

### Default build

```bash
make
```

Equivalent to:

```bash
packer fmt .
packer validate .
packer build .
```

### Override versions

```bash
make build AWS_REGION=us-west-2 CLICKHOUSE_VERSION=25.10.2.65
```

---

## Publishing AMI to SSM

After building:

```bash
make publish
```

This stores the most recent AMI ID in:

```
/ssm/path: /clickhouse/base/ami
```

Equivalent to:

```bash
aws ssm put-parameter \
  --name "/clickhouse/base/ami" \
  --type String \
  --overwrite \
  --value "$(make -s last-ami)"
```

---

## Using the AMI in Terraform

```hcl
data "aws_ssm_parameter" "clickhouse_ami" {
  name = "/clickhouse/base/ami"
}

locals {
  clickhouse_ami_id = data.aws_ssm_parameter.clickhouse_ami.value
}
```

Use it like:

```hcl
resource "aws_instance" "clickhouse" {
  ami           = local.clickhouse_ami_id
  instance_type = "m6i.large"
  ...
}
```

---

## When to Rebuild

Rebuild when:

* ClickHouse version changes
* Amazon Linux 2023 base image updates
* Install or config flow changes
* New packages or dependencies are required

Do **not** rebuild for:

* Schema changes
* Dashboard updates
* CDC wiring updates
* Runtime scripts or PoC logic

---

## Future Extensions

Potential AMI variants:

* `clickhouse-obs-base` – includes Prometheus/Grafana/Exporters
* `clickhouse-bootstrap` – pre-baked schema + config overlays
* Shared `harden-base.sh` applied to all infra AMIs

---

## Summary

This AMI gives you a **fast, lightweight, reproducible ClickHouse base image** for EC2. All PoC and runtime logic stays out of the AMI and is applied dynamically via Adage, userdata, or SSM.

This approach enables:

* Minimal blast radius for changes
* Consistent deploys across environments
* Reusable AMI lifecycle independent of runtime concerns
