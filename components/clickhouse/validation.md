# ClickHouse EC2 Bootstrap & Backup Validation

## IMDSv2 & Role Sanity

``` bash
# IMDSv2 token (6h)
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token"   -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# User-data (confirm what boot ran)
curl -sS -i -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/user-data

# Role name
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/)
echo "ROLE=$ROLE"

# Role creds JSON (proves IMDS & sts path work)
curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE | jq .
```

## ClickHouse Health

``` bash
systemctl status amazon-ssm-agent --no-pager
systemctl status clickhouse-server --no-pager

curl -s http://localhost:8123/ping   # expect: Ok.
clickhouse-client -q "SELECT version(), now()"

cat /var/local/BOOTSTRAP_OK
mount | grep ' /var/lib/clickhouse '
```

## S3 via AWS CLI (uses instance role)

``` bash
AWS_REGION=us-east-1
BACKUP_BUCKET=usekarma.dev-prod
BACKUP_PREFIX=clickhouse

aws sts get-caller-identity
echo "backup test $(date -Is)" > /tmp/test-backup.txt
aws s3 cp /tmp/test-backup.txt s3://$BACKUP_BUCKET/$BACKUP_PREFIX/test-backup.txt --region $AWS_REGION
aws s3 cp s3://$BACKUP_BUCKET/$BACKUP_PREFIX/test-backup.txt /tmp/test-restore.txt --region $AWS_REGION
cat /tmp/test-restore.txt
```

## Confirm ClickHouse Sees the S3 Disk

``` bash
clickhouse-client -q "SELECT name, type FROM system.disks"
# Expect to see: s3_backups
```

## ✅ Native Backup Using the S3 Disk

> Your disk endpoint already ends with `/$BACKUP_PREFIX/` --- so just
> pass a subfolder name.

``` bash
TS=$(date -u +%Y%m%dT%H%M%SZ)

# Create backup
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'auto-$TS/')"

# Verify in S3
aws s3 ls "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/auto-$TS/" --region $AWS_REGION --recursive

# Do we have the metadata table?
clickhouse-client -q "EXISTS TABLE system.backups"

# If that returned '1', list recent backups
clickhouse-client -q "DESCRIBE TABLE system.backups FORMAT Pretty"
```

## 🔁 Optional Restore Smoke Test

``` bash
TS_LATEST=$(clickhouse-client -q "SELECT name FROM system.backups ORDER BY create_time DESC LIMIT 1"             | sed 's|.*auto-||; s|/||g' || true)

# If you know the TS you used above, set TS_LATEST=$TS instead.

clickhouse-client --multiquery -q "
  CREATE DATABASE IF NOT EXISTS default_restored;
  RESTORE DATABASE default AS default_restored
    FROM Disk('s3_backups', 'auto-${TS_LATEST}/');
  SHOW DATABASES;
"
```
