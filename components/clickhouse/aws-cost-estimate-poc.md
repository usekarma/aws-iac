# Estimated AWS Cost for Redpanda + MongoDB + ClickHouse + Grafana + Kafka Connect/Streams (PoC)

This estimate assumes **us-east-1**, On-Demand Linux pricing, single-node Redpanda, separate Mongo, ClickHouse+Grafana colocated, and a Kafka Connect/Streams node.

---

## 1. Compute (hourly → monthly at ~730 hrs)

- **ClickHouse + Grafana — r6i.xlarge**: $0.252/hr → **~$184/mo**
- **Redpanda — c6i.large**: $0.085/hr → **~$62/mo**
- **MongoDB — r6i.large**: $0.126/hr → **~$92/mo**
- **Kafka Connect + Streams — t3.large**: $0.0832/hr → **~$61/mo**

**Compute subtotal:** ≈ **$399/mo**

---

## 2. Storage (gp3, per month)

- **Redpanda**: 200 GB × $0.08 ≈ **$16**
- **MongoDB**: 300 GB × $0.08 ≈ **$24**
- **ClickHouse**: 500 GB × $0.08 ≈ **$40**

If you provision **6k IOPS** and **250 MB/s throughput** for ClickHouse:
- Extra IOPS: 3k × $0.005 = **$15**
- Extra throughput: 125 MB/s × $0.04 = **$5**

**Storage subtotal:** baseline **$80/mo**, or **~$100/mo** with boosted IOPS/throughput.

---

## 3. Network

- **Same-AZ private traffic**: free.
- **Cross-AZ**: ~$0.01/GB each direction.
- For PoC, keep everything in one AZ to avoid data transfer charges.

---

## 4. Bottom Line (On-Demand)

- **Baseline PoC (no extra CH IOPS/throughput):** **~$479/mo**
- **With boosted CH gp3 (6k IOPS / 250 MB/s):** **~$499/mo**

---

## 5. Notes and Optimizations

- Use **Spot** for Connect/Streams box → cut cost by ~70–90%.
- Collapse **Connect+Streams** onto the CH host → save ~$61/mo (but adds contention).
- Redpanda could run on **t3.large** for lighter loads, but c6i.large safer.
- No license costs: Redpanda (OSS), MongoDB Community, ClickHouse, Grafana are free.

---
