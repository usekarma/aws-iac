-- 00_raw_mongo_cdc.sql
-- Raw Mongo CDC ingestion into ClickHouse
--
-- Expects the bootstrap script to replace:
--   {{KAFKA_BROKER}}
-- with the actual broker string (e.g. "redpanda:9092")
-- before executing this file.

CREATE DATABASE IF NOT EXISTS raw;

-- Kafka engine table consuming Mongo Debezium topics:
--   mongo.sales.customers
--   mongo.sales.vendors
--   mongo.sales.products
--   mongo.sales.inventory
--   mongo.sales.orders
--   mongo.reports.report_runs
--   mongo.reports.report_requests
--   mongo.reports.report_attempts
--   mongo.reports.dependency_calls
--   mongo.reports.outcomes
CREATE TABLE IF NOT EXISTS raw.kafka_mongo_cdc_raw
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
    kafka_broker_list    = '{{KAFKA_BROKER}}',
    kafka_topic_list     = 'mongo.sales.customers,mongo.sales.vendors,mongo.sales.products,mongo.sales.inventory,mongo.sales.orders,mongo.reports.report_runs,mongo.reports.report_requests,mongo.reports.report_attempts,mongo.reports.dependency_calls,mongo.reports.outcomes',
    kafka_group_name     = 'clickhouse_mongo_cdc',
    kafka_format         = 'JSONEachRow',
    kafka_num_consumers  = 1;

-- Wide CDC events table in ClickHouse
CREATE TABLE IF NOT EXISTS raw.mongo_cdc_events
(
    db                  String,     -- source database (e.g. "sales" or "reports")
    collection          String,     -- source collection (e.g. "orders", "customers", "report_runs")
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
DROP TABLE IF EXISTS raw.mv_mongo_cdc_events;

-- Materialized view: fan-in from the Kafka table into the wide CDC table
CREATE MATERIALIZED VIEW raw.mv_mongo_cdc_events
TO raw.mongo_cdc_events
AS
SELECT
    JSONExtractString(source, 'db')         AS db,
    JSONExtractString(source, 'collection') AS collection,
    op,
    ts_ms,
    toDateTime(ts_ms / 1000)                AS event_time,
    before                                  AS before_json,
    after                                   AS after_json,
    updateDescription                       AS update_description,
    transaction                             AS transaction_json
FROM raw.kafka_mongo_cdc_raw;
