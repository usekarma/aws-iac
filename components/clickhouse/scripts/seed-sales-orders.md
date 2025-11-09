
# seed-sales-orders.sh

Synthetic MongoDB order generator for CDC (Change Data Capture) pipelines.

This script generates realistic e-commerce order traffic into MongoDB (`sales.orders`)
for CDC pipelines such as **MongoDB → Kafka/Redpanda → ClickHouse → Grafana**.

Designed for **Adage** and **Karma** proof-of-concepts to simulate organic,
time-distributed data suitable for dashboards, latency measurements, and anomaly detection.

---

## 🧩 Overview

The script continuously:
- Inserts randomized **order documents** with realistic timestamps and prices  
- Simulates repeat customers and loyal buyer patterns  
- Randomly performs **updates (~40%)** and **deletes (~10%)**  
- Spreads timestamps across recent days to generate smooth time-series curves  
- Emits CDC events compatible with **Debezium MongoDB connectors**

---

## ⚙️ Configuration

| Variable | Default | Description |
|-----------|----------|-------------|
| `MONGO_HOST` | `127.0.0.1` | MongoDB host |
| `MONGO_PORT` | `27017` | MongoDB port |
| `DB_NAME` | `sales` | Database name |
| `COLL_NAME` | `orders` | Collection name |
| `SLEEP_SEC` | `1` | Delay between inserts |
| `COUNT` | (required) | Number of inserts to perform |
| `CUSTOMER_REPEAT_RATE` | *internal* | Approximate frequency of recurring customers |
| `DAYS_SPAN` | *7* | Range (days) for distributing `created_at` |

---

## 🚀 Usage

### 1️⃣ Basic sanity run
```bash
/usr/local/bin/seed-sales-orders.sh 100
```
Creates 100 simple orders over ~2 minutes.  
Ideal for confirming CDC flow from Mongo → Kafka → ClickHouse.

---

### 2️⃣ Stress test (fast large run)
```bash
SLEEP_SEC=0.001 /usr/local/bin/seed-sales-orders.sh 50000
```
Generates 50K orders with microsecond-level delay.  
Produces a dense, highly varied dataset for dashboard load testing.

---

### 3️⃣ Loyalty spike (repeated customers)
```bash
CUSTOMER_REPEAT_RATE=0.7 SLEEP_SEC=0.01 /usr/local/bin/seed-sales-orders.sh 15000
```
70% of orders come from repeat buyers.  
Graphs will show recognizable “customer streaks” in Grafana’s customer aggregation panels.

---

### 4️⃣ Day-night pattern simulation
```bash
DAYS_SPAN=5 SLEEP_SEC=0.02 /usr/local/bin/seed-sales-orders.sh 20000
```
Spreads `created_at` timestamps unevenly over several days (morning/evening bursts).  
Visually useful for time-series lag and diurnal load simulation.

---

### 5️⃣ Mixed traffic (insert + update + delete)
```bash
SLEEP_SEC=0.002 /usr/local/bin/seed-sales-orders.sh 30000
```
Generates roughly:
- 18K inserts  
- 9K updates  
- 3K deletes  

This produces the most dynamic CDC event mix — ideal for validating
materialized views and downstream data reconciliation.

---

## 🧮 Example Mongo Document

```json
{
  "order_id": "O000481",
  "customer_id": "C1042",
  "amount": 87.45,
  "currency": "USD",
  "status": "PROCESSING",
  "created_at": "2025-11-07T12:34:56Z",
  "updated_at": "2025-11-07T13:05:22Z"
}
```

---

## 📊 ClickHouse Exploration

**Daily sales totals**
```sql
SELECT
  toDate(created_at) AS day,
  sum(amount) AS total_amount,
  count() AS orders
FROM sales.orders
GROUP BY day
ORDER BY day;
```

**Top customers**
```sql
SELECT
  customer_id,
  count() AS orders,
  round(sum(amount), 2) AS total_spent
FROM sales.orders
GROUP BY customer_id
ORDER BY total_spent DESC
LIMIT 10;
```

**Event rhythm (inserts vs updates)**
```sql
SELECT
  toStartOfHour(updated_at) AS hour,
  countIf(status = 'NEW') AS new_orders,
  countIf(status = 'SHIPPED') AS shipped,
  countIf(status = 'CANCELLED') AS cancelled
FROM sales.orders
GROUP BY hour
ORDER BY hour;
```

---

## 🧰 Cleanup & Reset

To delete all existing orders from both MongoDB and ClickHouse:

```bash
# MongoDB cleanup
mongosh "mongodb://127.0.0.1:27017/sales" --eval 'db.orders.deleteMany({})'

# ClickHouse cleanup
clickhouse-client --query "
  TRUNCATE TABLE sales.orders;
  TRUNCATE TABLE sales.mv_sales_orders;
  TRUNCATE TABLE sales.kafka_sales_orders_raw;
"
```

Then reseed fresh data:
```bash
SLEEP_SEC=0.001 /usr/local/bin/seed-sales-orders.sh 50000
```

---

## 🧪 Observability Pairings

| Layer | Component | Purpose |
|-------|------------|----------|
| Source | MongoDB (`sales.orders`) | Raw CDC event source |
| Transport | Redpanda / Kafka | Debezium event bus |
| Sink | ClickHouse | Aggregated analytics store |
| View | Grafana | Visualization of metrics, trends, customer behavior |

Example dashboards:
- **Orders per day** (bar + line)
- **Revenue heatmap per customer**
- **CDC event velocity** (insert/update/delete counts)
- **Amount entropy** (variance over time)

---

## 🧱 Integration Notes

- Plug-and-play with `mongo-cdc-sales-orders` Debezium connector  
- Schema-aligned with ClickHouse ingestion (`kafka_sales_orders_raw → mv_sales_orders → orders`)  
- Can run standalone or under EC2/EKS `userdata.sh` bootstrap  
- Ideal for testing alert correlation and time-aligned event overlays in Karma

---

## 📜 License

MIT © usekarma.dev
