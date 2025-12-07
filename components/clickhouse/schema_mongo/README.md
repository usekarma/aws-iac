# MongoDB → Debezium → Kafka → ClickHouse CDC + SLA Demo

This demo sets up a complete end-to-end Change Data Capture (CDC) pipeline from MongoDB into ClickHouse through Debezium and Kafka (Redpanda). It now includes:

- A **sales domain** — customers, products, inventory, orders, vendors  
- A **reports / SLA domain** — report runs per subscriber with latency and failure data  

Everything is wired for Grafana so you can see both **business metrics** (orders, revenue, inventory) and **SLA behavior** (latency, outliers, failures) from the same CDC stream.

---

## 🧱 Components

| Layer         | Technology                               | Description |
|---------------|-------------------------------------------|-------------|
| Source (OLTP) | **MongoDB**                              | Operational data in two DBs: `sales` (customers, vendors, products, inventory, orders) and `reports` (`report_runs`) |
| CDC           | **Debezium MongoDB Connector (3.x)**     | Single “core” connector that streams both `sales.*` and `reports.report_runs` into Kafka topics with prefix `mongo.` |
| Transport     | **Kafka / Redpanda**                     | Kafka-compatible broker carrying Debezium CDC topics |
| Sink (raw)    | **ClickHouse 25.10.1**                   | Kafka ENGINE table + materialized view fan-in into a wide CDC table (one row per MongoDB change event) |
| Views (sales) | **ClickHouse SQL**                       | Typed analytical views: `sales.orders_v`, `sales.customers_v`, `sales.products_v`, `sales.inventory_v`, `sales.vendors_v` |
| Views (SLA)   | **ClickHouse SQL**                       | Typed views over `reports.report_runs` and SLA-oriented views (latency, outliers, breaches) in `reports` / `sla` DBs |
| Visualization | **Grafana**                              | Dashboards for CDC throughput, revenue trends, order lifecycle, and SLA behavior for report generation |

---

## ⚙️ Setup Overview

### 1️⃣ Initialize MongoDB Sales Schema

```bash
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/init-sales-db.js
```

This creates the `sales` database with collections and indexes for:

- `customers`
- `vendors`
- `products`
- `inventory`
- `orders`

All of these are **schema-only** (no data yet), designed to be CDC-friendly.

---

### 2️⃣ Seed MongoDB Sales Data

Populate realistic demo data for the sales domain:

```bash
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/seed-sales-data.js
```

This script generates:

- A set of customers, vendors, and products  
- Inventory snapshots  
- Time-spaced orders suitable for:
  - time-series plots,
  - vendor and product aggregations,
  - revenue analysis.

> To generate a larger dataset, adjust configuration (e.g. `NUM_CUSTOMERS`, `NUM_ORDERS`) inside `seed-sales-data.js` before running.

---

### 3️⃣ Initialize MongoDB Reports / SLA Schema

The SLA portion of the demo uses a separate `reports` database, with a single `report_runs` collection that tracks each report execution for a subscriber.

```bash
RESET_REPORTS_DB=true \
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/init-reports-schema.js
```

This script:

- Ensures the `reports` database exists  
- Ensures the `report_runs` collection exists  
- Clears any existing validator (permissive for the PoC)  
- Drops and recreates non-unique indexes for common access patterns:
  - `run_id`
  - `(subscriber_id, requested_at)`
  - `(status, requested_at)`
  - `(report_type, requested_at)`

`RESET_REPORTS_DB=true` makes the reset **destructive** for existing data; omit it if you want to preserve prior runs.

---

### 4️⃣ Seed Report Traffic for SLA Analysis

Populate the `reports.report_runs` collection with realistic, SLA-oriented traffic:

```bash
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/seed-reports-data.js
```

By default, this will:

- Generate roughly 6 hours of historical report runs
- Use multiple subscribers with tiers:
  - `enterprise`
  - `pro`
  - `free`
- Assign each run:
  - `run_id`
  - `subscriber_id`
  - `report_type` (e.g., `daily_summary`, `risk_scoring`)
  - `status` (`completed` or `failed`)
  - `requested_at`, `started_at`, `completed_at`
  - Optional `error_code` / `error_message` for failures
- Simulate:
  - Different latency profiles per tier
  - Occasional severe outliers
  - A small fraction of failures

This traffic is what drives the SLA views in ClickHouse.

---

### 5️⃣ Start Debezium MongoDB Connector

A single “core” Debezium connector (for example, `mongo-cdc-core`) streams both `sales.*` and `reports.report_runs` into Kafka. The bootstrap script `kconnect-mongo-bootstrap.sh` handles:

- Creating/updating the connector config at the Kafka Connect REST endpoint
- Including:
  - `sales` and `reports` databases
  - Collections:
    - `sales.customers`
    - `sales.vendors`
    - `sales.products`
    - `sales.inventory`
    - `sales.orders`
    - `reports.report_runs`
- Configuring simple JSON payloads (no Avro):
  - `key.converter`: JSON, `schemas.enable=false`
  - `value.converter`: JSON, `schemas.enable=false`

Topic naming is based on Debezium’s standard pattern with a `topic.prefix` (for example, `mongo.`). Adjust the connector config and ClickHouse schema together if you change topic names.

Run the bootstrap script on the Kafka Connect host:

```bash
/usr/local/bin/kconnect-mongo-bootstrap.sh
```

You can verify connector status via:

```bash
curl -s http://$KCONNECT_HOST:8083/connectors/mongo-cdc-core/status
```

---

### 6️⃣ Bootstrap ClickHouse CDC Schema

ClickHouse is provisioned on EC2 with:

- EBS data volume for `/var/lib/clickhouse`
- Prometheus / Grafana bundle for observability
- A CDC bootstrap script that pulls SQL schema from S3 and applies it.

The main entrypoint is:

```bash
/usr/local/bin/kafka-clickhouse-bootstrap.sh
```

This script:

1. Resolves the Redpanda/Kafka broker from `REDPANDA_HOST`
2. Syncs SQL files from S3, typically under a prefix like:

   ```text
   s3://<CLICKHOUSE_BUCKET>/<CLICKHOUSE_PREFIX>/schema_clickhouse/
     00_raw_mongo_cdc.sql
     10_*.sql
     20_*.sql
     30_*.sql
   ```

   into a local directory (e.g. `/usr/local/bin/schema_clickhouse`)

3. Applies `00_raw_mongo_cdc.sql` first, passing the broker via `--param kafka_broker_list=...` to create:

   - A Kafka ENGINE table for raw Debezium events (e.g. `raw.kafka_mongo_cdc_raw`)
   - A wide CDC table (e.g. `raw.mongo_cdc_events`) to store each event with:
     - `db`
     - `collection`
     - operation (`op`)
     - `ts_ms` / `event_time`
     - raw JSON payloads (`before_json`, `after_json`, etc.)
   - A materialized view to fan in from the Kafka table into the wide table

4. Applies all remaining `NN_*.sql` files in numerical order, which define:

   - **Sales domain views** in `sales`:
     - `sales.orders_v`
     - `sales.customers_v`
     - `sales.vendors_v`
     - `sales.products_v`
     - `sales.inventory_v`
   - **Reports domain views** in `reports` (e.g. `reports.report_runs_v`)
   - **SLA views** in `sla` (e.g. aggregate latency and breach indicators)

If you change topic names or want additional derived views, you do so in these `NN_*.sql` files.

---

### 7️⃣ Grafana Dashboards

Grafana is bootstrapped by `grafana-bootstrap.sh`, which:

- Registers ClickHouse, Prometheus, and other datasources
- Loads prebuilt dashboards for:
  - CDC ingestion health
  - Orders/revenue/inventory trends
  - SLA distributions and outliers for report runs

Once the ClickHouse schema and Mongo traffic are in place, the dashboards should start to show new events automatically.

---

## 🧪 Example Queries

### Sales Domain

```sql
-- New orders by day
SELECT
    toDate(order_time) AS day,
    count(*)          AS orders
FROM sales.orders_v
GROUP BY day
ORDER BY day;

-- Revenue by vendor
SELECT
    vendor_id,
    sum(total_amount) AS revenue
FROM sales.orders_v
GROUP BY vendor_id
ORDER BY revenue DESC;

-- Inventory trends
SELECT
    product_id,
    avg(available_qty) AS avg_available
FROM sales.inventory_v
GROUP BY product_id;
```

### Reports / SLA Domain

```sql
-- Latency distribution by subscriber tier (if tier is projected)
SELECT
    subscriber_id,
    avg(latency_ms)                        AS avg_latency,
    quantileExact(0.95)(latency_ms)        AS p95,
    sum(is_sla_breach)                     AS sla_breaches
FROM sla.report_runs_sla
GROUP BY subscriber_id
ORDER BY p95 DESC;

-- Failure rate and outliers by report type
SELECT
    report_type,
    count()                                AS runs,
    sum(status = 'failed')                 AS failures,
    sum(is_outlier)                        AS outliers,
    avg(latency_ms)                        AS avg_latency
FROM sla.report_runs_sla
GROUP BY report_type
ORDER BY runs DESC;

-- Timeline of report runs for a single subscriber
SELECT
    requested_at,
    report_type,
    status,
    latency_ms,
    is_sla_breach
FROM sla.report_runs_sla
WHERE subscriber_id = 'A100'
ORDER BY requested_at DESC
LIMIT 200;
```

(Exact column names may vary based on your `NN_*.sql` definitions, but this is the intended shape.)

---

## 📂 File Reference

| File / Dir                             | Purpose |
|----------------------------------------|---------|
| `init-sales-db.js`                     | Defines MongoDB `sales` schema (collections + indexes, no data) |
| `seed-sales-data.js`                   | Seeds `sales` data: customers, products, vendors, inventory, and orders |
| `init-reports-schema.js`              | Bootstraps `reports.report_runs` (permissive schema + indexes, optional reset) |
| `seed-reports-data.js`                | Seeds realistic `report_runs` traffic for SLA analysis |
| `kconnect-mongo-bootstrap.sh`         | Creates/updates Debezium connector for `sales.*` and `reports.report_runs` |
| `kafka-clickhouse-bootstrap.sh`       | Syncs ClickHouse schema SQL from S3 and applies raw + domain + SLA schema |
| `schema_clickhouse/00_raw_mongo_cdc.sql` | Creates raw Kafka table, wide CDC events table, and MV fan-in |
| `schema_clickhouse/10_*.sql`          | Sales domain typed views (`sales.*`) |
| `schema_clickhouse/20_*.sql`          | Reports domain typed views (`reports.*`) |
| `schema_clickhouse/30_*.sql`          | SLA-oriented views (`sla.*`) |
| `grafana-bootstrap.sh`                | Configures Grafana datasources and dashboards |
| `README.md`                           | Documentation for the full CDC + SLA demo |

---

## 🧠 Notes

- Mongo validators are intentionally **relaxed** for this PoC to simplify reseeding and schema changes.  
- All write activity in `sales` and `reports` flows into Kafka via Debezium and then into ClickHouse via the Kafka ENGINE + materialized view.  
- The **wide CDC table** is the single source of truth in ClickHouse; all domain and SLA views are projections of that history.  
- You can reset the demo at any time by:
  - Re-initializing Mongo (`init-sales-db.js`, `init-reports-schema.js`)
  - Reseeding (`seed-sales-data.js`, `seed-reports-data.js`)
  - Re-running `kafka-clickhouse-bootstrap.sh` if schema changes.

---

_Last updated: 2025-12-07 America/Chicago_
