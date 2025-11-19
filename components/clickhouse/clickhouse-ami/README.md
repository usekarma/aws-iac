# ClickHouse AMI (Amazon Linux 2023 + Packer)

A fast-booting **base AMI** with ClickHouse preinstalled.
All schema, Kafka tables, CDC, exporters, dashboards, backups, etc. are applied **at runtime**, not baked in.

---

## Build
```bash
make
```
Or with overrides:
```bash
make build AWS_REGION=us-west-2 CLICKHOUSE_VERSION=25.10.2.65
```

---

## Publish AMI ID to SSM
```bash
make publish
```
Writes to:
```
/clickhouse/base/ami
```

---

## Use in Terraform
```hcl
data "aws_ssm_parameter" "clickhouse_ami" {
  name = "/clickhouse/base/ami"
}

resource "aws_instance" "clickhouse" {
  ami           = data.aws_ssm_parameter.clickhouse_ami.value
  instance_type = "m6i.large"
}
```

---

## When to Rebuild
Rebuild if:
* ClickHouse version changes
* Amazon Linux 2023 base updates
* Install script changes

**Do NOT rebuild for:**
* Schema changes
* Kafka ENGINE tables
* Debezium config
* Dashboards / exporters
* PoC logic

These belong in **userdata or SSM bootstrap**.

---

## Key Reminders
* AMI is intentionally minimal and fast
* Systemd ClickHouse is installed + enabled
* `listen.xml` allows all interfaces — security via SGs
* Bootstrapping scripts run after launch
* Don’t put PoC logic in the AMI

---

## Cleaning Up Old AMIs

### List old AMIs
```bash
aws ec2 describe-images \
  --owners self \
  --filters "Name=name,Values=clickhouse-base-*" \
  --query 'Images[*].[ImageId,Name,CreationDate]' \
  --output table
```

### Deregister an AMI
```bash
aws ec2 deregister-image --image-id ami-1234567890abcdef0
```

### Find and delete orphan snapshots
```bash
aws ec2 describe-snapshots \
  --owner-ids self \
  --query 'Snapshots[?Description!=null && contains(Description, `ami-1234567890abcdef0`)].SnapshotId'
```
Delete:
```bash
aws ec2 delete-snapshot --snapshot-id snap-0123456789abcdef0
```

---

## TL;DR Workflow
```bash
make
make publish
terraform apply
# occasional cleanup:
aws ec2 deregister-image --image-id OLD_AMI
aws ec2 delete-snapshot --snapshot-id OLD_SNAP
