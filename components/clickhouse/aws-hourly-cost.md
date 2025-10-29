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
