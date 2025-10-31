# Observability Stack Validation (ClickHouse + Prometheus + Grafana + ALB)

## 0) Exports (edit for your env)
```bash
# ---- Runtime config (hosts come from your SSM config) ----
AWS_REGION=us-east-1

GRAFANA_HOST=grafana.usekarma.dev
PROM_HOST=prometheus.usekarma.dev
CH_HOST=clickhouse.usekarma.dev

# S3 backup location used by ClickHouse + CLI tests
BACKUP_BUCKET=usekarma.dev-prod
BACKUP_PREFIX=clickhouse

# (Optional) set to your ALB DNS if Route53 hasn’t propagated yet
ALB_DNS=$(aws elbv2 describe-load-balancers --region $AWS_REGION   | jq -r '.LoadBalancers[] | select(.LoadBalancerName | test("usekarma-observability")) | .DNSName' | head -1)

echo "ALB_DNS=${ALB_DNS}"
```

## 1) EC2 Bootstrap & IMDSv2 / Role Sanity
```bash
# IMDSv2 token
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token"   -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# Confirm user-data retrieved & ran
curl -sS -i -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/user-data | head -40

# Role name + creds (proves IMDS + role path)
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/)
echo "ROLE=$ROLE"

curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE | jq .
```

## 2) Core Services (local)
```bash
# Agents/services
systemctl status amazon-ssm-agent --no-pager
systemctl status clickhouse-server --no-pager || true

# ClickHouse local health
curl -s http://localhost:8123/ping  # expect: Ok.
clickhouse-client -q "SELECT version(), now()"

# Bootstrap marker and disk mount
cat /var/local/BOOTSTRAP_OK
mount | grep ' /var/lib/clickhouse '

# Prometheus local (if running on same box)
curl -s -o /dev/null -w "%{http_code}
" http://localhost:9090/-/ready   # 200
curl -s -o /dev/null -w "%{http_code}
" http://localhost:9090/-/healthy # 200
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets | length'

# Grafana local (if on same box, default 3000)
curl -s -o /dev/null -w "%{http_code}
" http://localhost:3000/api/health  # 200 if health endpoint enabled
curl -s -o /dev/null -w "%{http_code}
" http://localhost:3000/login       # often 200/302
```

## 3) S3 via AWS CLI (instance role)
```bash
aws sts get-caller-identity
echo "backup test $(date -Is)" > /tmp/test-backup.txt
aws s3 cp /tmp/test-backup.txt s3://$BACKUP_BUCKET/$BACKUP_PREFIX/test-backup.txt --region $AWS_REGION
aws s3 cp s3://$BACKUP_BUCKET/$BACKUP_PREFIX/test-backup.txt /tmp/test-restore.txt --region $AWS_REGION
diff -u /tmp/test-backup.txt /tmp/test-restore.txt && echo "S3 round-trip OK"
```

## 4) ClickHouse sees S3 Disk
```bash
clickhouse-client -q "SELECT name, type FROM system.disks"   # Expect row for: s3_backups
clickhouse-client -q "SELECT name, path FROM system.storages WHERE name LIKE '%s3%'" || true
```

## 5) ClickHouse Native Backup to S3 (Disk)
```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)

# Create backup
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'auto-$TS/')"

# Verify in S3
aws s3 ls "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/auto-$TS/" --region $AWS_REGION --recursive

# Check backup metadata
clickhouse-client -q "EXISTS TABLE system.backups"   # expect: 1
clickhouse-client -q "SELECT name, status, error FROM system.backups ORDER BY create_time DESC LIMIT 5 FORMAT Pretty"
```

### (Optional) Restore Smoke Test
```bash
TS_LATEST=$(clickhouse-client -q "SELECT name FROM system.backups ORDER BY create_time DESC LIMIT 1"   | sed 's|.*auto-||; s|/||g' || true)

clickhouse-client --multiquery -q "
  CREATE DATABASE IF NOT EXISTS default_restored;
  RESTORE DATABASE default AS default_restored
    FROM Disk('s3_backups', 'auto-${TS_LATEST}/');
  SHOW DATABASES;
"
```

## 6) ALB Listener / Rules / TLS (externally via hostnames)
```bash
for H in "$GRAFANA_HOST" "$PROM_HOST" "$CH_HOST"; do
  echo "----- $H -----"
  curl -sS -I "https://$H" | sed -n '1,10p'
  echo | openssl s_client -servername "$H" -connect "$H:443" 2>/dev/null     | openssl x509 -noout -issuer -subject -dates
done

# With forced resolve to ALB while DNS propagates
for H in "$GRAFANA_HOST" "$PROM_HOST" "$CH_HOST"; do
  echo "----- $H (forced) -----"
  curl --resolve "$H:443:$ALB_DNS" -sS -I "https://$H" | sed -n '1,10p'
done
```

## 7) Route53 DNS
```bash
for H in "$GRAFANA_HOST" "$PROM_HOST" "$CH_HOST"; do
  echo "----- dig $H -----"
  dig +short "$H" A
done
```

## 8) Target Group Health (ALB side)
```bash
ALB_ARN=$(aws elbv2 describe-load-balancers --region $AWS_REGION   | jq -r '.LoadBalancers[] | select(.DNSName=="'"$ALB_DNS"'") | .LoadBalancerArn')
echo "ALB_ARN=$ALB_ARN"

aws elbv2 describe-target-groups --region $AWS_REGION --load-balancer-arn "$ALB_ARN"   | jq -r '.TargetGroups[] | {Name:.TargetGroupName, Arn:.TargetGroupArn, Port:.Port}'

for TG_ARN in $(aws elbv2 describe-target-groups --region $AWS_REGION --load-balancer-arn "$ALB_ARN"                  | jq -r '.TargetGroups[].TargetGroupArn'); do
  echo "---- $TG_ARN ----"
  aws elbv2 describe-target-health --region $AWS_REGION --target-group-arn "$TG_ARN"     | jq -r '.TargetHealthDescriptions[] | {Id:.Target.Id, Port:.Target.Port, State:.TargetHealth.State, Reason:.TargetHealth.Reason}'
done
```

## 9) Grafana Quick Smoke (unauth paths)
```bash
curl -sI "https://$GRAFANA_HOST/api/health" | sed -n '1,6p' || true
curl -sI "https://$GRAFANA_HOST/login"      | sed -n '1,6p'
```

## 10) Prometheus Query API Smoke
```bash
curl -s "https://$PROM_HOST/api/v1/query?query=up" | jq '.status, (.data.result | length)'
curl -s "https://$PROM_HOST/api/v1/targets" | jq '.data | {active: (.activeTargets | length), dropped: (.droppedTargets | length)}'
```

## 11) ClickHouse Over ALB (HTTP interface)
```bash
curl -s "https://$CH_HOST/ping"                     # Ok.
curl -s "https://$CH_HOST/?query=SELECT%201"        # 1
curl -s "https://$CH_HOST/?query=SELECT%20now()"    # timestamp
```

## 12) Common Failures & Quick Fixes
- **ALB 5xx**: check TG health and `journalctl -u clickhouse-server`
- **Grafana /api/health returns 401/404**: switch ALB health path to `/login`
- **Prometheus /-/ready 404**: adjust TG health check path
- **Cert mismatch**: ensure all hosts are SANs in ACM cert
- **DNS not resolving**: use `--resolve $HOST:443:$ALB_DNS` until propagation
