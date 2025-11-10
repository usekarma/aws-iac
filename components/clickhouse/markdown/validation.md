# Full Stack Validation — ClickHouse + Redpanda + MongoDB + Prometheus + Grafana + ALB

This checklist gives copy‑pasteable commands to validate **every component** of your PoC:
- EC2 / IMDSv2 / SSM
- Storage mounts & service units
- **ClickHouse** (local + over ALB)
- **Redpanda** (broker + topic + produce/consume + admin API)
- **MongoDB** (service + replica set + network)
- **Prometheus** (targets, rules, queries)
- **Exporters** (Node Exporter, ClickHouse native /metrics)
- **Grafana** (API health, data source, dashboards)
- **ALB + ACM + Route53** (HTTPS & target health)
- **Backups to S3** (ClickHouse backup/restore disk)

> Replace placeholder values in the **Exports** section exactly once and keep reusing the variables.

---

## 0) Exports (edit for your env)
```bash
# ---- Runtime config ----
AWS_REGION=us-east-1

# Public hostnames fronted by ALB (ACM SANs)
GRAFANA_HOST=grafana.usekarma.dev
PROM_HOST=prometheus.usekarma.dev
CH_HOST=clickhouse.usekarma.dev

# Private broker / DB (from SSM runtime JSON)
RP_BROKERS="10.0.1.23:9092"            # format: ip:port,ip:port
MONGO_HOST="10.0.2.45"
MONGO_PORT=27017
MONGO_RS="rs0"

# S3 backup location used by ClickHouse + CLI tests
CLICKHOUSE_BUCKET=usekarma.dev-prod
CLICKHOUSE_PREFIX=clickhouse

# Grafana (optional) – use an API token if auth is enforced
# Create in Grafana UI: Settings → API Keys → Admin role
GRAFANA_TOKEN=""
GRAFANA_URL="https://$GRAFANA_HOST"

# ALB DNS (optional – if Route53 hasn’t propagated yet)
ALB_DNS=$(aws elbv2 describe-load-balancers --region $AWS_REGION   | jq -r '.LoadBalancers[] | select(.LoadBalancerName | test("usekarma-observability")) | .DNSName' | head -1)
echo "ALB_DNS=${ALB_DNS}"
```

---

## 1) EC2 Bootstrap & IMDSv2 / Role / SSM
```bash
# IMDSv2 token
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token"   -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# Confirm user-data retrieved & ran
curl -sS -i -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/user-data | head -40

# Role name + creds (proves IMDS + role path)
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/)
echo "ROLE=$ROLE"

curl -s -H "X-aws-ec2-metadata-token: $TOKEN"   http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE | jq .

# SSM agent & session manager
systemctl status amazon-ssm-agent --no-pager
```

**Expected:** SSM active, metadata returns temporary creds JSON.

---

## 2) Storage & Service Units (ClickHouse node)
```bash
# EBS mount
mount | grep ' /var/lib/clickhouse '

# Unit present & enabled (your userdata installed an [Install] and created the symlink if needed)
systemctl status clickhouse-server --no-pager
journalctl -u clickhouse-server -n 80 --no-pager | tail -n 40
```

**Expected:** mount present; service active; logs show listening ports.

---

## 3) ClickHouse — Local & Over ALB
```bash
# Local
curl -s http://localhost:8123/ping         # Ok.
clickhouse-client -q "SELECT version(), now()"

# Over ALB HTTPS (DNS) 
curl -s "https://$CH_HOST/ping"             # Ok.
curl -s "https://$CH_HOST/?query=SELECT%201"

# While DNS propagates, force resolve to ALB
curl --resolve "$CH_HOST:443:$ALB_DNS" -sI "https://$CH_HOST" | sed -n '1,8p'
echo | openssl s_client -servername "$CH_HOST" -connect "$CH_HOST:443" 2>/dev/null   | openssl x509 -noout -issuer -subject -dates
```

**Expected:** `Ok.` and `1`; certificate issuer/subject matches ACM.

---

## 4) Redpanda — Broker, Topic, Produce/Consume, Admin API
```bash
# Admin API readiness (default 9644 on broker host)
curl -s http://127.0.0.1:9644/v1/status/ready         # expect: "ready"
curl -s http://127.0.0.1:9644/v1/brokers | jq '.|length,.[]?.node_id' || true

# rpk quick info (requires rpk installed on this host)
rpk cluster info --brokers "$RP_BROKERS" || true
rpk topic list --brokers "$RP_BROKERS" || true

# Smoke produce/consume to the CH ingest topic
TOPIC="ch_ingest_normalized"
echo '{"id":1,"msg":"hello"}' | rpk topic produce "$TOPIC" --brokers "$RP_BROKERS" || true
rpk topic consume "$TOPIC" -n 1 --brokers "$RP_BROKERS" || true
```

**Expected:** admin `/ready` returns text `ready`; `rpk topic list` shows your topics; produce/consume works.

---

## 5) MongoDB — Service, Replica Set, Network
```bash
# Service
systemctl status mongod --no-pager
sudo journalctl -u mongod -n 80 --no-pager | tail -n 40

# Local RS status
mongosh --quiet --eval 'db.runCommand({ ping: 1 })'
mongosh --quiet --eval 'rs.status().ok'

# From ClickHouse/other host (network check)
nc -vz "$MONGO_HOST" "$MONGO_PORT" || true

# If RS not initiated yet (on mongo host)
mongosh --quiet --eval 'rs.initiate({_id:"'"$MONGO_RS"'", members:[{_id:0, host:"localhost:'"$MONGO_PORT"'"}]})' || true
```

**Expected:** `ping: 1` OK; `rs.status().ok` = 1; port reachable from CH and Connect hosts.

---

## 6) Prometheus — Targets, Readiness, Queries
```bash
# Local health (if running on same box)
curl -s -o /dev/null -w "%{http_code}
" http://localhost:9090/-/ready   # 200
curl -s -o /dev/null -w "%{http_code}
" http://localhost:9090/-/healthy # 200

# API: targets / up
curl -s http://localhost:9090/api/v1/targets | jq '.data | {active: (.activeTargets|length), dropped: (.droppedTargets|length)}'
curl -s http://localhost:9090/api/v1/query?query=up | jq '.status, (.data.result | length)'
```

**Expected:** ready/healthy 200; some `up{}` series including node exporter and clickhouse.

---

## 7) Exporters — Node & ClickHouse metrics
```bash
# Node Exporter bound to loopback
curl -s http://127.0.0.1:9100/metrics | head -5
curl -s http://127.0.0.1:9100/metrics | grep -E '^node_cpu_seconds_total' | head -3

# ClickHouse native metrics
curl -s http://127.0.0.1:9363/metrics | grep -E 'clickhouse_events|Query|RWLock|Context'
```

**Expected:** metric text exposed; Prometheus has scrape jobs named `node` and `clickhouse`.

---

## 8) Grafana — Health, Data Sources, Dashboards
```bash
# Health (unauth path, often 200/302)
curl -sI "https://$GRAFANA_HOST/login" | sed -n '1,6p'

# If a Grafana API token is available:
if [[ -n "$GRAFANA_TOKEN" ]]; then
  curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" "$GRAFANA_URL/api/health" | jq .
  echo "Data sources:"
  curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" "$GRAFANA_URL/api/datasources" | jq '.[].name'
  echo "Dashboards:"
  curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" "$GRAFANA_URL/api/search?query=" | jq '.[].title' | head -20
fi
```

**Expected:** `/login` reachable via HTTPS; API shows at least a **Prometheus** data source.

---

## 9) ALB + ACM + Route53
```bash
# HTTPS & certs for all fronted services
for H in "$GRAFANA_HOST" "$PROM_HOST" "$CH_HOST"; do
  echo "----- $H -----"
  curl -sS -I "https://$H" | sed -n '1,10p'
  echo | openssl s_client -servername "$H" -connect "$H:443" 2>/dev/null     | openssl x509 -noout -issuer -subject -dates
done

# Route53 resolution
for H in "$GRAFANA_HOST" "$PROM_HOST" "$CH_HOST"; do
  echo "dig $H ->"; dig +short "$H" A
done

# ALB Target Group health
ALB_ARN=$(aws elbv2 describe-load-balancers --region $AWS_REGION   | jq -r '.LoadBalancers[] | select(.DNSName=="'"$ALB_DNS"'") | .LoadBalancerArn')
echo "ALB_ARN=$ALB_ARN"

aws elbv2 describe-target-groups --region $AWS_REGION --load-balancer-arn "$ALB_ARN"   | jq -r '.TargetGroups[] | {Name:.TargetGroupName, Arn:.TargetGroupArn, Port:.Port}'

for TG_ARN in $(aws elbv2 describe-target-groups --region $AWS_REGION --load-balancer-arn "$ALB_ARN"                   | jq -r '.TargetGroups[].TargetGroupArn'); do
  echo "---- $TG_ARN ----"
  aws elbv2 describe-target-health --region $AWS_REGION --target-group-arn "$TG_ARN"     | jq -r '.TargetHealthDescriptions[] | {Id:.Target.Id, Port:.Target.Port, State:.TargetHealth.State, Reason:.TargetHealth.Reason}'
done
```

**Expected:** HTTPS 200/302; cert dates valid; TG health `healthy` for each target.

---

## 10) ClickHouse ↔ Redpanda Ingestion Path
```bash
# (Assuming your userdata created Kafka ENGINE table + MV)
clickhouse-client -q "SHOW TABLES LIKE 'kafka_src'"
clickhouse-client -q "SHOW TABLES LIKE 'events'"
clickhouse-client -q "SELECT count() FROM events"

# Produce 3 more test rows and verify count increases
for i in 101 102 103; do
  echo "{"id":$i,"msg":"probe"}"
done | rpk topic produce ch_ingest_normalized --brokers "$RP_BROKERS"

sleep 2
clickhouse-client -q "SELECT max(id), count() FROM events"
```

**Expected:** `events` count grows; `max(id)` reflects produced messages.

---

## 11) Backups to S3 (Disk) — Manual & Timer
```bash
# Manual backup
TS=$(date -u +%Y%m%dT%H%M%SZ)
clickhouse-client -q "BACKUP DATABASE default TO Disk('s3_backups', 'manual-${TS}/')"
aws s3 ls "s3://$CLICKHOUSE_BUCKET/$CLICKHOUSE_PREFIX/manual-${TS}/" --region $AWS_REGION --recursive

# Timer status & last run
systemctl status clickhouse-backup.timer --no-pager
journalctl -u clickhouse-backup.service -n 100 --no-pager | tail -n 40
```

**Expected:** S3 path populated; timer active; service logs show successful BACKUP.

---

## 12) Prometheus Sees Everything
```bash
# Expect at least these jobs:
# - prometheus (self)
# - node (node exporter)
# - clickhouse (/metrics on 9363)
curl -s http://localhost:9090/api/v1/targets   | jq -r '.data.activeTargets[] | [.labels.job, .labels.instance, .health, .lastScrape] | @tsv'   | column -t
```

**Expected:** rows for `node` and `clickhouse` with `up`/`healthy`.

---

## 13) Optional: Mongo & Redpanda Exporters
If you’ve deployed exporters for these (not included in your base userdata), validate similarly:

```bash
# MongoDB exporter example (if bound to 9216 locally)
curl -s http://127.0.0.1:9216/metrics | head -5

# Redpanda/Kafka exporter example (if bound to 9308)
curl -s http://127.0.0.1:9308/metrics | head -5
```

Add them to `/etc/prometheus/prometheus.yml` and confirm in **Section 12**.

---

## 14) Quick Fire Drills
```bash
# ALB 5xx? Check target health & service logs
journalctl -u grafana-server -n 100 --no-pager | tail -n 40
journalctl -u prometheus -n 100 --no-pager   | tail -n 40
journalctl -u clickhouse-server -n 100 --no-pager | tail -n 40

# TLS mismatch? Verify ACM cert contains all SANs (in AWS Console) and listener uses the right cert.
# DNS? Use --resolve trick until Route53 propagates:
curl --resolve "$GRAFANA_HOST:443:$ALB_DNS" -sI "https://$GRAFANA_HOST"
```

---

## 15) Clean Shutdown / Resume (State in S3)
- **ClickHouse**: covered via `BACKUP … TO Disk('s3_backups')` (Section 11).
- **Grafana**: export org/dashboards/datasources to S3 (API or filesystem) on a timer.
- **Prometheus**: snapshot `/var/lib/prometheus` to S3 before stop; restore on boot.
- **Redpanda**: for PoC, export topic snapshots with `rpk topic export …` (or MirrorMaker‑2 for larger flows).
- **MongoDB**: `mongodump` to S3; restore with `mongorestore` + re‑init RS.

(Automations for these can be added as systemd timers similar to the ClickHouse backup service.)

---

**All green?** You have end‑to‑end proof that:
- The ALB terminates TLS and routes to **Grafana**, **Prometheus**, and **ClickHouse**.
- **Prometheus** scrapes Node & ClickHouse metrics.
- **Redpanda** brokers are reachable; produce/consume works.
- **MongoDB** is healthy and reachable.
- **ClickHouse** ingests from Redpanda and backs up to **S3**.

---

# ✅ Validation Summary and Post-POC Notes

### When All Checks Pass
If every section above reports expected results, your stack is **production-grade in behavior** and **demo-ready**.  
You’ve validated:

| Layer | Validation | Result |
|-------|-------------|---------|
| **Network & Roles** | IMDSv2, IAM role, SSM agent functional | ✅ |
| **Compute & Storage** | EBS mounted, systemd units active | ✅ |
| **MongoDB** | RS initiated, reachable from CH & Connect | ✅ |
| **Redpanda** | Broker responsive, topics healthy, produce/consume works | ✅ |
| **Kafka Connect** | Debezium connector applied and running | ✅ |
| **ClickHouse** | Ingests Kafka topic via MV, backs up to S3 | ✅ |
| **Prometheus** | Targets healthy, metrics scraped | ✅ |
| **Grafana** | HTTPS reachable, dashboards imported | ✅ |
| **ALB + ACM + Route53** | Valid certs, healthy target groups | ✅ |

### Next Steps — From PoC to Production
1. **Secure all traffic:** enable TLS + SASL for Redpanda, SCRAM for Mongo, HTTPS for internal services.  
2. **Harden IAM:** scope EC2 roles to S3 prefixes only, restrict SSM session permissions.  
3. **Separate components:** turn each EC2 module into a reusable Adage component.  
4. **Add Terraform state isolation:** move to remote backend (e.g., S3 + DynamoDB lock).  
5. **Enable automated teardown:** wrap validation + destroy into a CI/CD job for repeatable demos.  
6. **Promote dashboards to GitOps:** export Grafana JSONs and manage via API or Terraform provider.

Once completed, this stack forms the **reference architecture for Adage + Karma observability pipelines** — a reproducible, full-path CDC and metrics demonstration.

---

_Last updated: 2025-11-08 16:10 _