#!/usr/bin/env bash
set -euo pipefail

# Optionally override this when calling the script:
#   REDPANDA_HOST=10.x.x.x ./clickhouse-schema-bootstrap.sh
BROKER="${REDPANDA_HOST:-10.42.140.128}"

clickhouse-client -n <<SQL
-- Ensure database exists
CREATE DATABASE IF NOT EXISTS sales;

-- Raw CDC stream from the single Debezium topic
-- Assumes Debezium sends fields:
--   before, after, updateDescription, source, op, ts_ms, transaction
-- for *all* collections under sales.*
CREATE TABLE IF NOT EXISTS sales.kafka_sales_cdc_raw
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
    kafka_topic_list    = 'mongo.sales.cdc',     -- <-- single CDC topic
    kafka_group_name    = 'clickhouse_sales_cdc',
    kafka_format        = 'JSONEachRow',
    kafka_num_consumers = 1;

-- Wide CDC events table in ClickHouse
-- One row per Debezium CDC event, regardless of collection.
CREATE TABLE IF NOT EXISTS sales.mongo_cdc_events
(
    db                  String,     -- source database (e.g. "sales")
    collection          String,     -- source collection (e.g. "orders", "customers")
    op                  String,     -- Debezium op: c,u,d,r
    ts_ms               UInt64,     -- Debezium event timestamp (millis)
    event_time          DateTime,   -- ts_ms converted to seconds
    before_json         String,     -- raw "before" document (JSON)
    after_json          String,     -- raw "after" document (JSON)
    update_description  String,     -- raw updateDescription JSON (if present)
    transaction_json    String      -- raw transaction JSON (if present)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_time, db, collection, op);

-- Recreate MV cleanly in case schema changed
DROP TABLE IF EXISTS sales.mv_mongo_cdc_events;

-- Materialized view: fan-in from the Kafka table into the wide CDC table
CREATE MATERIALIZED VIEW sales.mv_mongo_cdc_events
TO sales.mongo_cdc_events
AS
SELECT
    -- These keys assume Debezium's MongoDB connector "source" structure.
    -- Adjust JSON keys if your Debezium version uses different field names.
    JSONExtractString(source, 'db')         AS db,
    JSONExtractString(source, 'collection') AS collection,
    op,
    ts_ms,
    toDateTime(ts_ms / 1000)               AS event_time,
    before                                 AS before_json,
    after                                  AS after_json,
    updateDescription                      AS update_description,
    transaction                            AS transaction_json
FROM sales.kafka_sales_cdc_raw;
SQL
