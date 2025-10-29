# ClickHouse Component

Terraform component to deploy **ClickHouse on EC2** with:
- Dedicated **EBS** data volume
- **IAM** role for S3 backups
- Optional **Amazon MSK Serverless** (topic + IAM auth)
- **Systemd**-managed bootstrap & scheduled backups
- Discovery via **SSM Parameter Store** runtime JSON

---

## Inputs (from `config.json`)

- `vpc_nickname` – VPC component nickname (used to read `/iac/vpc/<nick>/runtime`)
- `s3_bucket_nickname` – S3 bucket component nickname (used to read `/iac/s3-bucket/<nick>/runtime`)
- `s3_bucket_prefix` – S3 key prefix for backups (e.g., `clickhouse/backups`)
- `instance_type` – default `m6i.large`
- `ebs_size_gb` – default `500`
- `ebs_type` – default `gp3` (with `ebs_iops`, `ebs_throughput`)
- `clickhouse_version` – default `24.8`
- `http_port` – default `8123`
- `tcp_port` – default `9000`
- `msk_enable` – default `true` (creates MSK Serverless + topic)
- `msk_topic_name` – default `clickhouse_ingest`

## Outputs

- `instance_id`, `private_ip`, `security_group_id`, `data_volume_id`
- `backup_bucket_name`, `backup_prefix`
- `msk_bootstrap_sasl_iam`, `msk_cluster_arn` (if enabled)
- `runtime_parameter_path` – SSM path with runtime JSON

---

## What gets created

- **EC2** (Amazon Linux 2023), **EBS** data volume mounted at `/var/lib/clickhouse`
- **SGs**: component SG + reference to VPC default SG (to reach SSM endpoints)
- **IAM**: `AmazonSSMManagedInstanceCore` + scoped S3 policy for backups
- **SSM runtime JSON** at `/iac/clickhouse/<nickname>/runtime`
- (**Optional**) **MSK Serverless** cluster & topic

---

## After `apply`: quick validation

```bash
# 1) Connect
aws ssm start-session --target <instance_id>

# 2) Check ClickHouse is up
curl -s localhost:8123 || sudo journalctl -u clickhouse-server -n 200 --no-pager

# 3) List MSK bootstrap (also in outputs)
aws ssm get-parameter --name /iac/clickhouse/<nickname>/runtime --with-decryption   --query 'Parameter.Value' --output text | jq .msk_bootstrap_sasl_iam

# 4) Check S3 backup folder
aws s3 ls s3://<backup-bucket>/<backup-prefix>/
```

---

## Scheduled backups (systemd timer)

Backups run on the instance via **systemd**. Default schedule: **daily at 02:00 UTC**.

- Service: `/etc/systemd/system/clickhouse-backup.service`
- Timer: `/etc/systemd/system/clickhouse-backup.timer`

**Start/Status/Logs**
```bash
sudo systemctl daemon-reload
sudo systemctl start clickhouse-backup.timer
sudo systemctl status clickhouse-backup.timer
journalctl -u clickhouse-backup.service -n 200 --no-pager
```

**Change the schedule**
```bash
# Edit only the timer (creates an override file)
sudo systemctl edit clickhouse-backup.timer
```
**Example override**
```ini
[Timer]
OnCalendar=daily
# Examples:
# OnCalendar=02:00         # every day at 02:00
# OnCalendar=*-*-* 02:00   # same as above (explicit)
# OnCalendar=hourly        # every hour
```

```bash
# Apply changes
sudo systemctl daemon-reload
sudo systemctl restart clickhouse-backup.timer
```

**Run a manual backup now**
```bash
sudo systemctl start clickhouse-backup.service
```

---

## Manual backup/restore commands

From the instance:

```bash
# Backup current DB to S3 (prefix is set in userdata)
clickhouse-client --query "BACKUP DATABASE default TO Disk('s3_backups', 'manual-$(date +%Y%m%d-%H%M%S)')"

# List objects in S3
aws s3 ls s3://<backup-bucket>/<backup-prefix>/

# Restore (example: latest manual/auto folder)
clickhouse-client --query "RESTORE DATABASE default FROM Disk('s3_backups', '<folder-name>') REPLACE;"
```

---

## Notes & gotchas

- **SSM endpoints** must exist in the VPC component and allow HTTPS from the VPC default SG.
- The ClickHouse instance SG is attached **in addition** to the VPC default SG so it can reach SSM endpoints and the MSK interface endpoints.
- Ensure your **S3 bucket policy** allows access from the instance role (the component creates an attached policy for List/Get/Put/Delete under the configured prefix).
- If MSK is enabled, the instance gets IAM permissions to call `kafka-cluster:Connect` and retrieve bootstrap brokers. You still need a consumer/ingestion pipeline (future ECS/Grafana/KConnect component).

---

## Removing

Stop the instance if you want to save $$. Destroying the component **does not** delete the S3 backups. The EBS data volume is destroyed with the instance unless you detach/preserve it yourself prior to `destroy`.

