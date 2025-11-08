#!/usr/bin/env bash
set -euo pipefail

# Optionally override this when calling the script:
BROKER="${REDPANDA_HOST:-10.42.140.128}"

clickhouse-client -n <<SQL
CREATE DATABASE IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.kafka_sales_orders_raw
(
    before            String,
    after             String,
    updateDescription String,
    source            String,
    op                String,
    ts_ms             UInt64,
    transaction       String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list   = '${BROKER}:9092',
    kafka_topic_list    = 'sales.sales.orders',
    kafka_group_name    = 'clickhouse_sales_orders',
    kafka_format        = 'JSONEachRow',
    kafka_num_consumers = 1;

CREATE TABLE IF NOT EXISTS sales.orders
(
    mongo_id    String,
    order_id    String,
    customer_id String,
    amount      Float64,
    currency    String,
    created_at  DateTime64(3)
)
ENGINE = MergeTree
ORDER BY (created_at, order_id);

DROP TABLE IF EXISTS sales.mv_sales_orders;

CREATE MATERIALIZED VIEW sales.mv_sales_orders
TO sales.orders
AS
SELECT
    JSONExtractString(after, '_id', '\$oid')          AS mongo_id,
    JSONExtractString(after, 'order_id')              AS order_id,
    JSONExtractString(after, 'customer_id')           AS customer_id,
    JSONExtractFloat(after,  'amount')                AS amount,
    JSONExtractString(after, 'currency')              AS currency,
    toDateTime64(
        JSONExtractInt(after, 'created_at', '\$date') / 1000.0,
        3
    ) AS created_at
FROM sales.kafka_sales_orders_raw
WHERE op = 'c';
SQL
