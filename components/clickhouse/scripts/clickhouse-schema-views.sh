#!/usr/bin/env bash
set -euo pipefail

# This script assumes the wide CDC table already exists:
#   sales.mongo_cdc_events
# created by your main schema bootstrap.

clickhouse-client -n <<'SQL'
CREATE DATABASE IF NOT EXISTS sales;

-- Clean up any old views
DROP VIEW IF EXISTS sales.orders_v;
DROP VIEW IF EXISTS sales.customers_v;
DROP VIEW IF EXISTS sales.products_v;
DROP VIEW IF EXISTS sales.vendors_v;
DROP VIEW IF EXISTS sales.inventory_v;

-- Orders view (typed projection from mongo_cdc_events)
CREATE VIEW sales.orders_v AS
SELECT
    db,
    collection,
    op                      AS cdc_op,
    ts_ms,
    event_time              AS cdc_event_time,

    JSONExtractString(after_json, '_id',    '$oid')  AS mongo_id,
    JSONExtractString(after_json, 'order_id')        AS order_id,
    JSONExtractString(after_json, 'customer_id')     AS customer_id,
    JSONExtractFloat(after_json,  'amount')          AS amount,
    JSONExtractString(after_json, 'currency')        AS currency,
    toDateTime64(
        JSONExtractInt(after_json, 'created_at', '$date') / 1000.0,
        3
    ) AS created_at
FROM sales.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'orders'
  AND op IN ('c','u');

-- Customers view
CREATE VIEW sales.customers_v AS
SELECT
    db,
    collection,
    op                      AS cdc_op,
    ts_ms,
    event_time              AS cdc_event_time,

    JSONExtractString(after_json, '_id',         '$oid')  AS mongo_id,
    JSONExtractString(after_json, 'customer_id')          AS customer_id,
    JSONExtractString(after_json, 'first_name')           AS first_name,
    JSONExtractString(after_json, 'last_name')            AS last_name,
    JSONExtractString(after_json, 'email')                AS email,
    JSONExtractString(after_json, 'segment')              AS segment,
    toDateTime64(
        JSONExtractInt(after_json, 'created_at', '$date') / 1000.0,
        3
    ) AS created_at,
    toDateTime64(
        JSONExtractInt(after_json, 'updated_at', '$date') / 1000.0,
        3
    ) AS updated_at
FROM sales.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'customers'
  AND op IN ('c','u');

-- Products view
CREATE VIEW sales.products_v AS
SELECT
    db,
    collection,
    op                      AS cdc_op,
    ts_ms,
    event_time              AS cdc_event_time,

    JSONExtractString(after_json, '_id',        '$oid')   AS mongo_id,
    JSONExtractString(after_json, 'product_id')          AS product_id,
    JSONExtractString(after_json, 'name')                AS name,
    JSONExtractString(after_json, 'category')            AS category,
    JSONExtractFloat(after_json,  'price')               AS price,
    JSONExtractFloat(after_json,  'cost')                AS cost,
    JSONExtractString(after_json, 'vendor_id')           AS vendor_id,
    toDateTime64(
        JSONExtractInt(after_json, 'created_at', '$date') / 1000.0,
        3
    ) AS created_at
FROM sales.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'products'
  AND op IN ('c','u');

-- Vendors view
CREATE VIEW sales.vendors_v AS
SELECT
    db,
    collection,
    op                      AS cdc_op,
    ts_ms,
    event_time              AS cdc_event_time,

    JSONExtractString(after_json, '_id',      '$oid')     AS mongo_id,
    JSONExtractString(after_json, 'vendor_id')           AS vendor_id,
    JSONExtractString(after_json, 'name')                AS name,
    JSONExtractString(after_json, 'country')             AS country,
    JSONExtractFloat(after_json,  'rating')              AS rating,
    toDateTime64(
        JSONExtractInt(after_json, 'created_at', '$date') / 1000.0,
        3
    ) AS created_at
FROM sales.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'vendors'
  AND op IN ('c','u');

-- Inventory view
CREATE VIEW sales.inventory_v AS
SELECT
    db,
    collection,
    op                      AS cdc_op,
    ts_ms,
    event_time              AS cdc_event_time,

    JSONExtractString(after_json, '_id',           '$oid')   AS mongo_id,
    JSONExtractString(after_json, 'inventory_id')           AS inventory_id,
    JSONExtractString(after_json, 'product_id')             AS product_id,
    JSONExtractString(after_json, 'warehouse_id')           AS warehouse_id,
    JSONExtractInt(after_json,    'quantity_on_hand')       AS quantity_on_hand,
    JSONExtractInt(after_json,    'reorder_point')          AS reorder_point,
    toDateTime64(
        JSONExtractInt(after_json, 'updated_at', '$date') / 1000.0,
        3
    ) AS updated_at
FROM sales.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'inventory'
  AND op IN ('c','u');
SQL
