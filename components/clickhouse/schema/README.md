# MongoDB → Debezium → Kafka → ClickHouse CDC Demo

This demo sets up a complete end-to-end Change Data Capture (CDC) pipeline from MongoDB into ClickHouse through Debezium and Kafka (Redpanda). It includes realistic data for a sales domain — customers, products, inventory, orders, and vendors — and provides ready-to-use scripts for schema creation, seeding, and analytical visualization in Grafana.

---

## 🧱 Components

| Layer | Technology | Description |
|--------|-------------|--------------|
| Source | **MongoDB** | Operational data source with 5 related collections (`customers`, `vendors`, `products`, `inventory`, `orders`) |
| CDC | **Debezium MongoDB Connector (v3.3.1.Final)** | Streams all collections from the `sales` database into a single topic `mongo.sales.cdc` |
| Transport | **Kafka / Redpanda** | Message broker for CDC events |
| Sink | **ClickHouse 25.10.1** | Receives CDC events via Kafka ENGINE table `sales.kafka_sales_cdc_raw` and stores parsed records in `sales.mongo_cdc_events` |
| Views | **ClickHouse SQL** | Typed analytical views for `orders_v`, `customers_v`, `products_v`, `inventory_v`, `vendors_v` |
| Visualization | **Grafana** | Dashboards for CDC metrics, revenue trends, and order lifecycles |

---

## ⚙️ Setup Overview

### 1️⃣ Initialize MongoDB Schema

```bash
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/init-sales-db.js
```

This creates the `sales` database with collections and indexes for:

- `customers`
- `vendors`
- `products`
- `inventory`
- `orders`

### 2️⃣ Seed MongoDB Data

Populate realistic demo data:

```bash
mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/seed-sales-data.js
```

This script generates customers, products, vendors, and time‑spaced orders suitable for CDC and time‑series visualization.

> To generate a larger dataset, adjust `NUM_CUSTOMERS` and `NUM_ORDERS` inside `seed-sales-data.js` before running.

### 3️⃣ Start Debezium MongoDB Connector

A single connector (`mongo-cdc-sales`) streams *all collections* under `sales.*` to **one topic**:

```jsonc
"transforms.route.regex": ".*",
"transforms.route.replacement": "mongo.sales.cdc"
```

### 4️⃣ Bootstrap ClickHouse

ClickHouse is provisioned on EC2 with:

- EBS data volume `/var/lib/clickhouse`
- S3 backup disk for manual/daily backups
- Prometheus/Grafana observability bundle
- Kafka→ClickHouse bootstrap script that creates:

```sql
CREATE TABLE sales.kafka_sales_cdc_raw (... ENGINE = Kafka ...);
CREATE TABLE sales.mongo_cdc_events (... ENGINE = MergeTree ...);
CREATE MATERIALIZED VIEW sales.mv_mongo_cdc_events AS SELECT ...;
```

If a previous backup exists in S3, the instance automatically restores from the **latest `manual-*` snapshot** during first boot.

### 5️⃣ Apply Typed Views

Once ingestion is working, run:

```bash
/usr/local/bin/clickhouse-schema-views.sh
```

This creates typed projections such as:

- `sales.orders_v`
- `sales.customers_v`
- `sales.vendors_v`
- `sales.products_v`
- `sales.inventory_v`

Each view filters and expands JSON fields from the wide `mongo_cdc_events` table.

---

## 🧪 Example Queries

```sql
-- New orders by day
SELECT toDate(event_time) AS day, count() FROM sales.orders_v GROUP BY day ORDER BY day;

-- Revenue by vendor
SELECT vendor_id, sum(total_amount) FROM sales.orders_v GROUP BY vendor_id ORDER BY sum(total_amount) DESC;

-- Inventory trends
SELECT product_id, avg(available_qty) FROM sales.inventory_v GROUP BY product_id;
```

---

## 📂 File Reference

| File | Purpose |
|------|----------|
| `init-sales-db.js` | Defines MongoDB schema (collections, indexes only) |
| `seed-sales-data.js` | Populates MongoDB with temporal data for CDC testing |
| `kconnect-mongo-bootstrap.sh` | Configures Debezium connector `mongo-cdc-sales` |
| `kafka-clickhouse-bootstrap.sh` | Creates ClickHouse Kafka source, wide table, MV |
| `clickhouse-schema-views.sh` | Builds typed views from the wide CDC table |
| `README.md` | Documentation for the full demo setup |

---

## 🧠 Notes

- All documents include `created_at` and `updated_at` timestamps for CDC.  
- CDC events flow into **`mongo.sales.cdc`** (single topic).  
- ClickHouse auto-ingests new events via `mv_mongo_cdc_events`.  
- You can reset the demo any time by reseeding Mongo and running the view script again.

---

_Last updated: 2025-11-10 America/Chicago_
