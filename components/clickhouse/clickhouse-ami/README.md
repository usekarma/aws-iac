# AMI Build & Metadata Pipeline  
### ClickHouse • MongoDB • Redpanda  
### (Base AMIs + SSM Metadata Contracts)

This directory builds the **three base AMIs** required by the PoC:

- **ClickHouse AMI**  
- **MongoDB AMI**  
- **Redpanda AMI**

These AMIs intentionally contain **only the OS + system-level server packages + exporters**.  
No schema, dashboards, flows, or CDC logic is baked in — those run at runtime.

AMI metadata is published to SSM so Terraform can consume *all required matching values*.

---

# 1. Makefile Targets

From inside the AMI component directory:

```
make clickhouse-ami     # Build ClickHouse AMI + write SSM
make mongo-ami          # Build Mongo AMI + write SSM
make redpanda-ami       # Build Redpanda AMI + write SSM
make amis               # Build ALL of them
```

---

# 2. Optional Makefile Overrides

## Global

```
AWS_REGION=us-east-1
AWS_PROFILE=prod-iac
IAC_PREFIX=/iac
COMPONENT_NAME=clickhouse
```

## ClickHouse

```
CLICKHOUSE_ROOT_GB=30
CLICKHOUSE_VERSION_TRACK=24.8
CLICKHOUSE_PROMETHEUS_VERSION=2.53.0
CLICKHOUSE_NODE_EXPORTER_VER=1.8.2
```

## Mongo

```
MONGO_ROOT_GB=30
MONGO_MAJOR=7
MONGO_EXPORTER_VERSION=0.40.0
MONGO_NODE_EXPORTER_VER=1.8.2
```

## Redpanda

```
REDPANDA_ROOT_GB=30
REDPANDA_VERSION=23.3.0
REDPANDA_NODE_EXPORTER_VER=1.8.2
```

### Example

```
make clickhouse-ami   AWS_REGION=us-west-2   AWS_PROFILE=prod   CLICKHOUSE_VERSION_TRACK=25.10.2.65
```

---

# 3. What Each Target Does

Every `*-ami` target performs:

1. `packer fmt`
2. `packer validate`
3. `packer build`
4. Parses AMI ID from Packer output
5. Writes SSM parameter:

```
${IAC_PREFIX}/${COMPONENT_NAME}/ami/<kind>
```

Where `<kind>` is:

- `base`
- `mongo`
- `redpanda`

---

# 4. SSM Parameter JSON (The Contract Terraform Consumes)

These JSON documents must contain **every value** Terraform must match.

---

## 4.1 ClickHouse

SSM path:

```
/iac/clickhouse/ami/base
```

JSON:

```json
{
  "ami_id": "ami-xxxxxxxxxxxx",
  "root_volume_gb": 30,
  "clickhouse_version": "24.8",
  "prometheus_version": "2.53.0",
  "node_exporter_version": "1.8.2"
}
```

---

## 4.2 Mongo

SSM path:

```
/iac/clickhouse/ami/mongo
```

JSON:

```json
{
  "ami_id": "ami-yyyyyyyyyyyy",
  "root_volume_gb": 30,
  "mongo_major": "7",
  "mongo_exporter_version": "0.40.0",
  "node_exporter_version": "1.8.2"
}
```

---

## 4.3 Redpanda

SSM path:

```
/iac/clickhouse/ami/redpanda
```

JSON:

```json
{
  "ami_id": "ami-zzzzzzzzzz",
  "root_volume_gb": 30,
  "redpanda_version": "23.3.0",
  "node_exporter_version": "1.8.2"
}
```

---

# 5. Terraform Only Needs These JSON Docs

Terraform will always read from SSM and configure EC2:

- AMI ID  
- root volume size  
- major versions  
- exporter versions  

This ensures the **AMI → Terraform → userdata** contract **always matches**.

---

# 6. When You Need to Rebuild

Rebuild AMIs when **any** of these change:

- OS packages
- ClickHouse / MongoDB / Redpanda versions
- Prometheus
- Node Exporter
- Systemd or bootstrap scripts

Do **not** rebuild AMIs for:

- schema  
- CDC  
- dashboards  
- Grafana  
- KConnect  
- PoC logic  

Those are runtime.

---

# 7. AMI Cleanup

List:

```
aws ec2 describe-images   --owners self   --filters "Name=name,Values=*-base-*"   --query 'Images[*].[ImageId,Name,CreationDate]'   --output table
```

Deregister:

```
aws ec2 deregister-image --image-id AMI_ID
```

Find snapshots:

```
aws ec2 describe-snapshots   --owner-ids self   --query "Snapshots[?contains(Description, 'AMI_ID')].SnapshotId"
```

Delete:

```
aws ec2 delete-snapshot --snapshot-id SNAP_ID
```

---

# 8. TL;DR

```
make amis
terraform apply
```
