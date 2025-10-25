# ClickHouse

Single EC2 running ClickHouse with EBS persistence, private by default.  

## What it does

- Reads VPC details from `/iac/vpc/<nickname>/runtime` (or your override).
- Creates a **security group** (`<nick>-sg-clickhouse`) with **no ingress** by default.
- Allows ingress on **8123** (and 9000) **only** from `allowed_security_group_ids` and/or `allowed_cidrs`.
- Launches an **Amazon Linux 2023** EC2 instance (default `m6i.large`) in a **private subnet** with **no public IP**.
- Attaches an **EBS data volume** (default **500 GB gp3**) mounted at `/var/lib/clickhouse`.
- Installs and starts **ClickHouse server**.
- Optional **S3 backup bucket** (create or reuse).
- Optional **Route53 A record** (usually a **private** zone), pointing to the **private IP**.
- Publishes **one SSM parameter** with runtime JSON.

## Config (from `aws-config`)

Example `iac/prod/clickhouse/usekarma-dev/config.json`:

```json
{
  "nickname": "use-karma-dev",
  "vpc_runtime_path": "/iac/vpc/use-karma-dev/runtime",

  "instance_type": "m6i.large",
  "ebs_size_gb": 500,

  "allowed_security_group_ids": [
    "/iac/vpc/use-karma-dev/runtime:default_sg_id", 
    "sg-0123456789abcdef0"
  ],
  "allowed_cidrs": [],

  "create_dns_record": true,
  "hosted_zone_id": "Z1234567890ABC", 
  "record_name": "clickhouse.usekarma.dev.",

  "create_backup_bucket": false,
  "backup_bucket_name": "usekarma-clickhouse-backups",
  "backup_prefix": "prod/clickhouse",

  "tags": { "Environment": "prod", "Project": "clickhouse", "Owner": "usekarma" }
}
```
Tip: If you store SG IDs in SSM, resolve them in Terragrunt and pass into locals.config before terraform runs (same pattern you already use).

## Outputs / Contract

- runtime_parameter_path → SSM path (JSON) with:

```json
{
  "instance_id": "...",
  "private_ip": "10.42.1.23",
  "security_group_id": "sg-...",
  "data_volume_id": "vol-...",
  "http_port": 8123,
  "tcp_port": 9000,
  "dns_record": "clickhouse.usekarma.dev.",
  "backup_bucket_name": "usekarma-clickhouse-backups",
  "backup_prefix": "prod/clickhouse",
  "vpc_id": "vpc-...",
  "subnet_id": "subnet-..."
}
```

Downstream components (Grafana, Kafka Connect) can read this single parameter and wire up security rules (e.g., allow Grafana SG → ClickHouse 8123).

## Start/Stop

Instance state is independent—EBS persists. You can tag stacks and start/stop together (e.g., with a make up/down target).


---

## Quick notes / choices baked in

- **Private by default**: tasks/services (Grafana) should connect over VPC; expose Grafana publicly if needed.
- **Ingress model**: specify **which SGs** may reach ClickHouse (cleaner than opening CIDRs).
- **DNS**: record points to **private IP**; set `hosted_zone_id` to a **private hosted zone** associated with your VPC, or to public if you really want it public (not recommended).
- **Backups**: minimal helper; feel free to swap to `clickhouse-backup` or EBS snapshots later.
