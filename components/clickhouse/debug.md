### Get a token (valid 6 hours) / fetch user-data (print headers to see status)
```
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -sS -i -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/user-data
```

### Check ClickHouse status
```
systemctl status amazon-ssm-agent
systemctl status clickhouse-server
clickhouse-client --query 'SELECT version()'
cat /var/local/BOOTSTRAP_OK
mount | grep ' /var/lib/clickhouse '
```

### Confirm S3 role
```
TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/info
```

### Confirm S3 connectivity
```
# Sanity check environment – should use EC2 role
aws sts get-caller-identity

# Create a test file
echo "backup test $(date)" > /tmp/test-backup.txt

BACKUP_BUCKET="usekarma.dev-prod"
BACKUP_PREFIX="clickhouse"

# Upload to the backup prefixaws s3 cp /tmp/test-backup.txt s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/test-backup.txt

# Fetch it back
aws s3 cp s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/test-backup.txt /tmp/test-restore.txt
cat /tmp/test-restore.txt
```

### Validate with ClickHouse Native Backup
```
AWS_REGION=us-east-1

-- From clickhouse-client

clickhouse-client --multiquery -q "
BACKUP DATABASE default TO S3(
  'https://my-bucket-name.s3.amazonaws.com/clickhouse/backups/ch-test-backup',
  'us-east-1',
  'aws'
);
"

clickhouse-client --multiquery -q "
RESTORE DATABASE default AS default_restored
  FROM S3(
    'https://${BACKUP_BUCKET}.s3.amazonaws.com/${BACKUP_PREFIX}/ch-test-backup',
    '${AWS_REGION}',
    'aws'
);
"

clickhouse-client -q "SHOW BACKUPS;"
```