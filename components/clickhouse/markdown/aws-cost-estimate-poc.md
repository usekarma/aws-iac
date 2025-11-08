# Hourly AWS Cost Estimate (On-Demand vs Spot)

This covers a PoC with Redpanda, MongoDB, ClickHouse+Grafana, and Kafka Connect/Streams in **us-east-1**.

---

## 1. Compute (per hour)

| Node                  | Instance   | On-Demand | Spot (typical) |
|-----------------------|------------|-----------|----------------|
| ClickHouse + Grafana  | r6i.xlarge | $0.252/hr | ~$0.109/hr |
| Redpanda broker       | c6i.large  | $0.085/hr | ~$0.035/hr |
| MongoDB               | r6i.large  | $0.126/hr | ~$0.04–0.06/hr |
| Kafka Connect+Streams | t3.large   | $0.083/hr | ~$0.02–0.04/hr |

**Totals**  
- On-Demand: ≈ **$0.546/hr**  
- Spot: ≈ **$0.224/hr** (midpoint estimate)

---

## 2. Storage (per hour)

gp3 pricing ($0.08/GB-month):  
- Redpanda 200 GB → $16/mo → **$0.022/hr**  
- MongoDB 300 GB → $24/mo → **$0.033/hr**  
- ClickHouse 500 GB → $40/mo → **$0.055/hr**  

**Storage subtotal:** ≈ **$0.11/hr**

With boosted ClickHouse gp3 (6k IOPS / 250 MB/s): +$20/mo → **+0.027/hr**.

---

## 3. Grand Total

- **On-Demand (baseline):** $0.546 + $0.11 ≈ **$0.66/hr**  
- **On-Demand (with CH boost):** ≈ **$0.69/hr**  
- **Spot (baseline):** $0.224 + $0.11 ≈ **$0.33/hr**  
- **Spot (with CH boost):** ≈ **$0.36/hr**

---

## 4. Notes

- Spot savings can be **50–70%**, but interruptions possible.  
- Keep everything in **one AZ** to avoid cross-AZ charges.  
- No software license costs: Redpanda OSS, MongoDB Community, ClickHouse, Grafana are all free.

---

# 5. Daily and Monthly Projections

| Mode | Hourly | Daily (24h) | Monthly (720h) |
|------|---------|-------------|----------------|
| On‑Demand (baseline) | $0.66 | $15.84 | **$475/mo** |
| On‑Demand (boosted)  | $0.69 | $16.56 | **$498/mo** |
| Spot (baseline)      | $0.33 | $7.92 | **$238/mo** |
| Spot (boosted)       | $0.36 | $8.64 | **$259/mo** |

---

# 6. Cost Optimization Opportunities

### a) Instance right‑sizing
- **ClickHouse:** use `r6i.large` (2 vCPU / 16 GiB) for light workloads → saves ≈ $0.13/hr.  
- **Kafka Connect:** scale horizontally with **1‑task Fargate** containers to pay per second.  
- **MongoDB:** consider `t3.large` for low CDC traffic.

### b) Storage efficiency
- Move backups to **S3 Standard‑IA** or **S3 Glacier Instant Retrieval**.  
- Use **EBS gp3** with 3k IOPS baseline; only boost when sustained throughput required.  
- Automate daily `fstrim` and metric‑based volume right‑sizing.

### c) Networking
- Co‑locate all nodes in the **same VPC and AZ** to eliminate inter‑AZ data transfer.  
- Use **PrivateLink** or **VPC endpoints** for S3 and SSM to avoid public egress.  
- Disable public NAT Gateway if you rely only on SSM Session Manager.

### d) Compute purchasing
- Use **Savings Plans** (1‑year, 50%+ savings) once steady.  
- Convert to **Spot Fleet** with fallback On‑Demand capacity for production.  
- Explore **Lambda or ECS Fargate** for temporary connectors.

### e) Monitoring budget
Set a **CloudWatch alarm** or **AWS Budgets alert** at 80% of expected monthly cap.  
Sample: `$250` budget for Spot PoC.

---

# 7. Quick Cost Reference Summary

| Tier | Infra Scope | Approx $/month | Comment |
|------|--------------|----------------|----------|
| 🧪 PoC (Spot, single‑AZ) | 4 EC2 + EBS + S3 | **$230–260** | Your current setup |
| 🧩 Adage Demo (multi‑AZ, same stack) | 6 EC2 + ALB + ACM + Route53 | **$400–450** | Adds fault tolerance |
| 🏗️ Pre‑prod (HA × 2) | 8–10 EC2 + MSK + RDS | **$850–1000** | MSK replaces Redpanda, adds redundancy |

---

_Last updated: 2025-11-08 16:11 _