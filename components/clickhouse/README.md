# ClickHouse Component (EC2)

Terraform component to deploy **ClickHouse on EC2** with:

- Dedicated **EBS** data volume
- **IAM** role–based backups to **Amazon S3** (no AK/SK in config)
- Optional **Amazon MSK Serverless** (topic + IAM auth)
- **systemd**-managed bootstrap & scheduled backups
- Discovery via **SSM Parameter Store** runtime JSON

---

## Inputs (from `config.json`)

- `vpc_nickname` – VPC component nickname (used to read `/iac/vpc/<nick>/runtime`)
- `s3_bucket_nickname` – S3 bucket component nickname (used to read `/iac/s3-bucket/<nick>/runtime`)
- `s3_bucket_prefix` – S3 key prefix for backups (e.g., `clickhouse/backups`)
- `instance_type` – default `m6i.large`
- `ebs_size_gb` – default `500`
- `ebs_type` – default `gp3` (`ebs_iops`, `ebs_throughput` supported)
- `clickhouse_version` – default `25.9` (tested with 25.9.4)
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
- **Security Groups**: component SG + reference to VPC default SG (reach SSM endpoints)
- **IAM**: `AmazonSSMManagedInstanceCore` + scoped S3 policy for `{bucket}/{prefix}`
- **SSM runtime JSON** at `/iac/clickhouse/<nickname>/runtime`
- (**Optional**) **MSK Serverless** cluster & topic

---

## User‑data highlights (what the instance does on first boot)

- Installs **amazon-ssm-agent**, **clickhouse-server**, **clickhouse-client**
- Mounts the EBS device at `/var/lib/clickhouse` (XFS), updates `/etc/fstab`
- Writes **ClickHouse** config fragments under `/etc/clickhouse-server/config.d/` using `<clickhouse>` root:
  - `10-data-path.xml` → `<path>/var/lib/clickhouse/</path>` (+ optional `<tmp_path>`)
  - `20-network.xml` → `listen_host=0.0.0.0`, `http_port`, `tcp_port`
  - `30-s3-backup.xml` → defines `Disk('s3_backups')` with:
    ```xml
    <type>s3_plain</type>
    <endpoint>https://s3.$${AWS_REGION}.amazonaws.com/$${BACKUP_BUCKET}/$${BACKUP_PREFIX}/</endpoint>
    <use_environment_credentials>true</use_environment_credentials>
    <region>$${AWS_REGION}</region>
    <metadata_path>/var/lib/clickhouse/disks/s3_backups/</metadata_path>
    ```
    and whitelists it for backups:
    ```xml
    <backups><allowed_disk>s3_backups</allowed_disk></backups>
    ```
  - **Note:** `$${...}` prevents Terraform from expanding vars; bash expands at boot.
- Starts ClickHouse via **systemd** and works around missing `systemd-sysv-install` by creating the `wants/` symlink if needed.
- Installs a **systemd timer** to run a daily backup (service runs `BACKUP DATABASE default TO Disk('s3_backups', 'auto-<ts>/')`).

---

## After `apply`: quick validation

```bash
# 1) Connect
aws ssm start-session --target <instance_id>

# 2) ClickHouse is up
curl -s http://localhost:8123/ping  # expect: Ok.
clickhouse-client -q "SELECT version(), now()"

# 3) Data mount is in place
mount | grep ' /var/lib/clickhouse '

# 4) Role & S3 (uses instance profile)
aws sts get-caller-identity
aws s3 ls s3://<backup-bucket>/<backup-prefix>/
```

---

## Scheduled backups (systemd timer)

Default schedule: **daily** (see timer for exact `OnCalendar`).

- Service: `/etc/systemd/system/clickhouse-backup.service`
- Timer:   `/etc/systemd/system/clickhouse-backup.timer`

**Start/Status/Logs**
```bash
sudo systemctl daemon-reload
sudo systemctl start clickhouse-backup.timer
sudo systemctl status clickhouse-backup.timer --no-pager
journalctl -u clickhouse-backup.service -n 200 --no-pager
```

**Change the schedule**
```bash
sudo systemctl edit clickhouse-backup.timer    # adds an override file
# Example override:
# [Timer]
# OnCalendar=02:00
# RandomizedDelaySec=10m

sudo systemctl daemon-reload
sudo systemctl restart clickhouse-backup.timer
```

**Run a manual backup now**
```bash
sudo systemctl start clickhouse-backup.service
```

---

## Manual backup/restore

```bash
# Backup current DB to S3 (prefix already embedded in the Disk endpoint)
TS=$(date -u +%Y%m%dT%H%M%SZ)
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'manual-${TS}/')"

# Verify in S3
aws s3 ls s3://<backup-bucket>/<backup-prefix>/manual-${TS}/ --recursive

# Restore into a new DB (structure+data)
clickhouse-client -q "CREATE DATABASE IF NOT EXISTS default_restored"
clickhouse-client -q "RESTORE DATABASE default AS default_restored FROM Disk('s3_backups', 'manual-${TS}/')"
```

> **Important:** Do **not** use `TO S3('https://…', 'region', 'aws')` unless you supply AK/SK. That form does **not** use the instance role. The **Disk('s3_backups', …)** path does.

---

## Troubleshooting

**No logs and service inactive**
```bash
sudo mkdir -p /var/log/clickhouse-server /var/lib/clickhouse
sudo chown -R clickhouse:clickhouse /var/log/clickhouse-server /var/lib/clickhouse
sudo systemctl status clickhouse-server --no-pager
sudo journalctl -u clickhouse-server -n 200 --no-pager
```

**`systemctl enable` fails with `systemd-sysv-install` missing**
```bash
# Manually install the unit
sudo cp -f /usr/lib/systemd/system/clickhouse-server.service /etc/systemd/system/clickhouse-server.service
grep -q '^[[]Install[]]' /etc/systemd/system/clickhouse-server.service || sudo bash -lc 'cat >>/etc/systemd/system/clickhouse-server.service <<EOF

[Install]
WantedBy=multi-user.target
EOF'
sudo systemctl daemon-reload
sudo mkdir -p /etc/systemd/system/multi-user.target.wants
sudo ln -sf /etc/systemd/system/clickhouse-server.service              /etc/systemd/system/multi-user.target.wants/clickhouse-server.service
sudo systemctl start clickhouse-server
```

**Config won’t parse / server won’t start**
```bash
# Temporarily disable S3 disk fragment and retry
sudo mv /etc/clickhouse-server/config.d/30-s3-backup.xml{,.off}
sudo systemctl restart clickhouse-server || sudo -u clickhouse /usr/bin/clickhouse-server --config-file=/etc/clickhouse-server/config.xml
# Inspect: /var/lib/clickhouse/preprocessed_configs/config.xml
```

**IMDSv2 & IAM sanity (no AK/SK expected)**
```bash
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token"   -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/)
curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE | jq .
```

**Listing backups (schema varies by version)**
```bash
# If available
clickhouse-client -q "EXISTS TABLE system.backups"
# Example for 25.9 schema (fields may differ)
clickhouse-client -q "DESCRIBE TABLE system.backups FORMAT Pretty"
clickhouse-client -q "SELECT id, name, status, error, start_time, end_time FROM system.backups ORDER BY start_time DESC FORMAT Pretty"
```

---

## Removal

- Terminate the instance to stop charges.
- **S3 backups are NOT deleted** by `destroy`.
- If you want to preserve the EBS volume, detach it before destroying the instance.

---

_Last updated: 2025-10-29 00:51 UTC_
