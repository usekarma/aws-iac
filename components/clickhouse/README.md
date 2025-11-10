# ClickHouse Component (EC2) — **Redpanda-ready + S3 Backups + Observability**

![ClickHouse Component](../../img/clickhouse.drawio.png)

Terraform component to deploy **ClickHouse on EC2** with:

- Dedicated **EBS** data volume  
- **IAM role**–based backups to **Amazon S3**  
- **Kafka / Redpanda** ingest wiring (Kafka engine table + Materialized View)  
- **systemd**-managed bootstrap & **manual backups**  
- Optional local **observability bundle**: **Prometheus**, **Grafana**, **Node Exporter**, **ClickHouse /metrics**  
- Discovery via **SSM Parameter Store** runtime JSON  

---

## Inputs (from `config.json`)

**Required Infra:**
- `vpc_nickname` – VPC component nickname (used to read `/iac/vpc/<nick>/runtime`)
- `s3_bucket_nickname` – S3 bucket component nickname (used to read `/iac/s3-bucket/<nick>/runtime`)
- `clickhouse_bucket` – S3 bucket name for ClickHouse assets and backups (e.g., `usekarma.dev-prod`)
- `clickhouse_prefix` – S3 key prefix (e.g., `clickhouse`); backups stored under `<prefix>/backups/`

**EC2 & Storage:**
- `instance_type` – default `m6i.large`
- `ebs_size_gb` – default `500`
- `ebs_type` – default `gp3` (`ebs_iops`, `ebs_throughput` supported)

**ClickHouse:**
- `clickhouse_version` – default `25.9` (tested with 25.9.4)
- `http_port` – default `8123`
- `tcp_port` – default `9000`

**Kafka / Redpanda Ingest:**
- `redpanda_enable` – default `true` (deploys single-node Redpanda EC2 in same VPC)
- `redpanda_topic` – default `clickhouse_ingest`
- `redpanda_partitions` – default `3`
- `redpanda_retention_ms` – default `604800000` (7 days)

**Observability (optional):**
- `enable_observability` – default `true`
- `prometheus_version` – default `2.53.1`
- `node_exporter_version` – default `1.8.2`

---

## Outputs

- `instance_id`, `private_ip`, `security_group_id`, `data_volume_id`
- `clickhouse_bucket`, `clickhouse_prefix`
- `runtime_parameter_path` – SSM path with runtime JSON  

If `redpanda_enable = true`, also:
- `redpanda_instance_id`, `redpanda_private_ip`, `redpanda_security_group_id`
- `redpanda_brokers` (e.g., `10.0.1.23:9092`) written into runtime JSON

---

## What Gets Created

- **EC2** (Amazon Linux 2023), **EBS** data volume mounted at `/var/lib/clickhouse`
- **Security Groups:** component SG + VPC default SG (for SSM)
- **IAM:** `AmazonSSMManagedInstanceCore` + scoped S3 policy for `{clickhouse_bucket}/{clickhouse_prefix}/*`
- **SSM runtime JSON** at `/iac/clickhouse/<nickname>/runtime`
- (**Optional**) **Redpanda** single node (PLAINTEXT in-VPC for PoC)
- (**Optional**) **Prometheus** (9090), **Grafana** (3000), **Node Exporter** (9100), **ClickHouse /metrics** (9363)

---

## User-data Highlights (First Boot)

- Installs `amazon-ssm-agent`, `clickhouse-server`, `clickhouse-client`
- Mounts EBS volume at `/var/lib/clickhouse` (XFS)
- Writes config fragments under `/etc/clickhouse-server/config.d/`:

  - `10-data-path.xml`
  - `20-network.xml`
  - `30-s3-backup.xml` → defines S3 disk:

    ```xml
    <type>s3_plain</type>
    <endpoint>https://$${CLICKHOUSE_BUCKET}.s3.$${AWS_REGION}.amazonaws.com/$${CLICKHOUSE_PREFIX}/backups/</endpoint>
    <use_environment_credentials>true</use_environment_credentials>
    <region>$${AWS_REGION}</region>
    <metadata_path>/var/lib/clickhouse/disks/s3_backups/</metadata_path>
    <backups><allowed_disk>s3_backups</allowed_disk></backups>
    ```

- Creates **Kafka ENGINE** source table and **Materialized View** into a MergeTree sink  
- **Manual backup only** (default; no systemd timer)  
- If `enable_observability = true`, installs Prometheus, Grafana, Node Exporter, and exposes ClickHouse metrics at `:9363`

---

## Validation After Apply

```bash
aws ssm start-session --target <instance_id>

curl -s http://localhost:8123/ping          # expect: Ok.
clickhouse-client -q "SELECT version(), now()"
mount | grep '/var/lib/clickhouse'
aws sts get-caller-identity
aws s3 ls s3://<clickhouse-bucket>/<clickhouse-prefix>/backups/
clickhouse-client -q "SHOW TABLES"
```

---

## Manual Backup / Restore

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)

# Create backup
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'manual-${TS}/')"

# Verify in S3
aws s3 ls s3://<clickhouse-bucket>/<clickhouse-prefix>/backups/manual-${TS}/ --recursive

# Restore example
clickhouse-client -q "CREATE DATABASE IF NOT EXISTS default_restored"
clickhouse-client -q "RESTORE DATABASE default AS default_restored FROM Disk('s3_backups', 'manual-${TS}/')"
```

> Backups use instance IAM role credentials via `Disk('s3_backups', …)` — **no AK/SK needed**.

---

_Last updated: 2025-11-09 America/Chicago_
