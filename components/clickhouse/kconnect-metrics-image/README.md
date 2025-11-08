# ClickHouse Component (EC2) — **Redpanda-ready + S3 backups + Observability**

![ClickHouse Component](../../img/clickhouse.drawio.png)

Terraform component to deploy **ClickHouse on EC2** with:

- Dedicated **EBS** data volume  
- **IAM role**–based backups to **Amazon S3** (no AK/SK in config)  
- **Kafka/Redpanda** ingest wiring (Kafka engine table + MV) — **no MSK required**  
- **systemd**-managed bootstrap & scheduled backups  
- Optional local **observability bundle**: **Prometheus**, **Grafana**, **Node Exporter**, **ClickHouse /metrics**  
- Discovery via **SSM Parameter Store** runtime JSON

---

## Inputs (from `config.json`)

Required infra lookups:
- `vpc_nickname` – VPC component nickname (used to read `/iac/vpc/<nick>/runtime`)
- `s3_bucket_nickname` – S3 bucket component nickname (used to read `/iac/s3-bucket/<nick>/runtime`)
- `s3_bucket_prefix` – S3 key prefix for backups (e.g., `clickhouse/backups`)

EC2 & storage:
- `instance_type` – default `m6i.large`
- `ebs_size_gb` – default `500`
- `ebs_type` – default `gp3` (`ebs_iops`, `ebs_throughput` supported)

ClickHouse:
- `clickhouse_version` – default `25.9` (tested with 25.9.4)
- `http_port` – default `8123`
- `tcp_port` – default `9000`

**Kafka / Redpanda ingest (PoC-friendly):**
- `redpanda_enable` – default `true` (creates single-node Redpanda EC2 in same VPC)
- `redpanda_topic` – default `clickhouse_ingest`
- `redpanda_partitions` – default `3`
- `redpanda_retention_ms` – default `604800000` (7d)
- _(If you run Redpanda elsewhere, set `redpanda_enable=false` and pass a brokers string via your own SSM/vars.)_

Observability (optional, all local to the CH host):
- `enable_observability` – default `true`
- `prometheus_version` – default `2.53.1`
- `node_exporter_version` – default `1.8.2`

---

## Outputs

- `instance_id`, `private_ip`, `security_group_id`, `data_volume_id`
- `backup_bucket_name`, `backup_prefix`
- `runtime_parameter_path` – SSM path with runtime JSON

If `redpanda_enable=true`, also:
- `redpanda_instance_id`, `redpanda_private_ip`, `redpanda_security_group_id`
- `redpanda_brokers` (e.g., `10.0.1.23:9092`) written into runtime JSON

---

## What gets created

- **EC2** (Amazon Linux 2023), **EBS** data volume mounted at `/var/lib/clickhouse`
- **Security Groups**: component SG + reference to VPC default SG (so the host can reach **SSM** endpoints)
- **IAM**: `AmazonSSMManagedInstanceCore` + scoped **S3** policy for `{bucket}/{prefix}`
- **SSM runtime JSON** at `/iac/clickhouse/<nickname>/runtime`
- (**Optional**) **Redpanda** single node (PLAINTEXT in-VPC for PoC), topic created with RF=1
- (**Optional**) **Prometheus** (9090), **Grafana** (3000), **Node Exporter** (9100), **ClickHouse /metrics** (9363)

---

## User-data highlights (first boot on the CH host)

- Installs **amazon-ssm-agent**, **clickhouse-server**, **clickhouse-client**
- Mounts the EBS device at **`/var/lib/clickhouse`** (XFS), updates `/etc/fstab`
- Writes **ClickHouse** config fragments under `/etc/clickhouse-server/config.d/` using `<clickhouse>` root:
  - `10-data-path.xml` → `<path>/var/lib/clickhouse/</path>`, `<tmp_path>`
  - `20-network.xml` → `listen_host=0.0.0.0`, `http_port`, `tcp_port`
  - `30-s3-backup.xml` → defines **Disk('s3_backups')** with:
    ```xml
    <type>s3_plain</type>
    <endpoint>https://$${BACKUP_BUCKET}.s3.$${AWS_REGION}.amazonaws.com/$${BACKUP_PREFIX}/</endpoint>
    <use_environment_credentials>true</use_environment_credentials>
    <region>$${AWS_REGION}</region>
    <metadata_path>/var/lib/clickhouse/disks/s3_backups/</metadata_path>
    <backups><allowed_disk>s3_backups</allowed_disk></backups>
    ```
    > `$${...}` prevents Terraform from expanding vars; bash expands them at boot.
- Ensures the **systemd unit has an `[Install]` section** and, on platforms without `systemd-sysv-install`, creates the `multi-user.target.wants/` symlink so **enable** works reliably.
- Creates **Kafka ENGINE** source table and **materialized view** to a MergeTree sink (topic/brokers from Redpanda or your provided brokers).
- Installs **systemd timer** to run a daily **BACKUP** to S3:  
  `BACKUP DATABASE default TO Disk('s3_backups', 'auto-<ts>/')`
- If `enable_observability=true`:
  - Installs **Prometheus** from tarball and runs as a systemd service on **9090** with scrape jobs for `prometheus`, `node_exporter (127.0.0.1:9100)`, and **ClickHouse** `:9363`
  - Installs **Grafana OSS** from repo and enables service on **3000**
  - Installs **Node Exporter** (loopback only) and enables service on **9100**
  - Enables **ClickHouse Prometheus endpoint** on **9363**

---

## After `apply`: quick validation

```bash
aws ssm start-session --target <instance_id>
curl -s http://localhost:8123/ping  # expect: Ok.
clickhouse-client -q "SELECT version(), now()"
mount | grep ' /var/lib/clickhouse '
aws sts get-caller-identity
aws s3 ls s3://<backup-bucket>/<backup-prefix>/
clickhouse-client -q "SHOW TABLES"
clickhouse-client -q "SELECT count() FROM events"
```

---

## Scheduled backups (systemd timer)

Default schedule: **daily** (`OnCalendar=daily`, randomized 10m).

- Service: `/etc/systemd/system/clickhouse-backup.service`  
- Timer:   `/etc/systemd/system/clickhouse-backup.timer`

---

## Manual backup/restore

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'manual-${TS}/')"
aws s3 ls s3://<backup-bucket>/<backup-prefix>/manual-${TS}/ --recursive
clickhouse-client -q "CREATE DATABASE IF NOT EXISTS default_restored"
clickhouse-client -q "RESTORE DATABASE default AS default_restored FROM Disk('s3_backups', 'manual-${TS}/')"
```

> **Do not** use `TO S3('https://…', 'region', 'aws')` unless you supply AK/SK.  
> The **Disk('s3_backups', …)** path **uses the instance role**.

---

_Last updated: 2025-10-30 19:06 America/Chicago_

---

# Full POC Deployment — Mongo → Redpanda → ClickHouse → Grafana

This proof‑of‑concept demonstrates a **complete CDC pipeline** that provisions, wires, and visualizes data flow end‑to‑end.

## Architecture Overview

```text
MongoDB (CDC source)
   ↓  Debezium Mongo Connector (Kafka Connect)
Redpanda (Kafka-compatible broker)
   ↓
ClickHouse (sink + metrics)
   ↓
Prometheus → Grafana (observability)
```

### Components

| Layer | Technology | Purpose |
|-------|-------------|----------|
| Source | MongoDB | CDC origin; replica set; Node + Mongo exporters |
| Transport | Redpanda | Kafka-compatible broker for CDC topics |
| Processing | Kafka Connect | Debezium MongoDB source connector |
| Sink | ClickHouse | Consumes Kafka topic into table (via ENGINE + MV) |
| Observability | Prometheus + Grafana | Unified metrics + dashboards |

### Deployment Sequence

1. `terraform apply` — provisions EC2 (Mongo, Redpanda, ClickHouse) and ECS/Fargate (Kafka Connect)
2. EC2 instances bootstrap via `userdata.sh.tmpl` scripts:
   - Mount EBS
   - Install core services and exporters
   - Register runtime details in **SSM Parameter Store**
3. Grafana auto‑configures via `grafana-bootstrap.sh`
4. Debezium connector deployed by `kconnect-mongo-bootstrap.sh.tmpl`
5. `seed-sales-orders.sh` generates traffic; CDC flows from Mongo → Redpanda → ClickHouse
6. Grafana dashboards auto‑imported for Mongo, Redpanda, ClickHouse, Prometheus, Node Exporter

### Key Validation Commands

```bash
# Mongo verification
aws ssm start-session --target <mongo_instance_id>
mongosh "mongodb://localhost:27017" --eval "rs.status()"

# Redpanda topics
aws ssm start-session --target <redpanda_instance_id>
rpk topic list

# ClickHouse CDC ingestion
aws ssm start-session --target <clickhouse_instance_id>
clickhouse-client -q "SHOW TABLES"
clickhouse-client -q "SELECT * FROM sales.orders LIMIT 5"

# Grafana access (via ALB DNS)
open http://<alb_dns>:3000
```

### Operational Notes

- All components are private (no public IPs).
- Instance roles handle S3 + SSM access (no static credentials).
- Backups scheduled daily via systemd timers.
- Entire stack rebuildable with a single `terraform destroy && terraform apply`.

---

_Last updated: 2025-11-08 16:07 _