# NiFi SQS-to-Postgres Demo: Checklist and Structure

This outlines the steps and structure for a minimal end-to-end demo that moves messages from an SQS queue into a Postgres database using Apache NiFi running on EKS.

---

## Components Required (All from `aws-iac`)

* [x] `eks-cluster/` — Provision EKS, IRSA-ready
* [x] `sqs-queue/` — Create input queue, expose metadata
* [x] `rds-postgres/` — Create target DB, expose JDBC info
* [x] `irsa-role/` — IAM role for NiFi pod to access SQS (reader)

---

## Supporting Scripts

* [x] `eks-cluster/use.sh` — Set kubeconfig context via Parameter Store

---

## NiFi Runtime Setup (Manual or Helm-driven)

* [ ] Deploy NiFi using Helm

  * Uses `eks-cluster` context from `use.sh`
  * Passes JDBC + SQS info using `--set` values or custom `values.yaml`
* [ ] Load basic NiFi flow:

  * Processor chain: `ConsumeSQS` → `UpdateRecord` → `PutDatabaseRecord`
  * Can be loaded via UI or uploaded via REST or ConfigMap

---

## Test Workflow

* [ ] Send test JSON payload to SQS:

```bash
aws sqs send-message \
  --queue-url $(aws ssm get-parameter --name /iac/sqs-queue/default/runtime/queue_url --query 'Parameter.Value' --output text) \
  --message-body '{"id": 123, "name": "demo"}'
```

* [ ] Connect to Postgres and verify data landed:

```bash
psql $(aws ssm get-parameter --name /iac/rds-postgres/default/runtime/jdbc_url --with-decryption --query 'Parameter.Value' --output text)
```

---

## File Structure Example (Demo Repo)

```
nifi-demo/
├── README.md
├── flows/
│   └── sqs-to-postgres.xml
├── values/
│   └── nifi-values.yaml
├── scripts/
│   └── test-publish-sqs.sh
└── helm/
    └── deploy-nifi.sh
```

---

## Optional Enhancements

* [ ] Add `s3-bucket/` for dead-letter archive
* [ ] Enable NiFi provenance and logs to S3 or EFS
* [ ] Auto-deploy NiFi flow via REST or ConfigMap injection
* [ ] Add metrics via Prometheus + Grafana stack

---

## Goal

Have a real, reproducible demo that:

* Provisions infra with Adage (`aws-iac`)
* Deploys NiFi with runtime values
* Moves data from SQS to Postgres in a live system
