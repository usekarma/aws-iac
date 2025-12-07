-- 10_sales_domain.sql
-- Domain views for the SALES database
-- Built over raw.mongo_cdc_events

CREATE DATABASE IF NOT EXISTS sales;

-- Orders
CREATE OR REPLACE VIEW sales.orders_v AS
SELECT
    db,
    collection,
    op              AS cdc_op,
    ts_ms,
    event_time,
    JSONExtractString(after_json, 'order_id')      AS order_id,
    JSONExtractString(after_json, 'customer_id')   AS customer_id,
    JSONExtractFloat(after_json,  'amount')        AS amount,
    JSONExtractString(after_json, 'currency')      AS currency,
    JSONExtractString(after_json, 'status')        AS status,
    JSONExtractString(after_json, 'vendor_id')     AS vendor_id,
    JSONExtractString(after_json, '_id', '$oid')   AS mongo_id
FROM raw.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'orders';


-- Customers
CREATE OR REPLACE VIEW sales.customers_v AS
SELECT
    JSONExtractString(after_json, 'customer_id')    AS customer_id,
    JSONExtractString(after_json, 'name')           AS name,
    JSONExtractString(after_json, 'email')          AS email,
    JSONExtractString(after_json, '_id', '$oid')    AS mongo_id,
    event_time,
    op AS cdc_op
FROM raw.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'customers';


-- Vendors
CREATE OR REPLACE VIEW sales.vendors_v AS
SELECT
    JSONExtractString(after_json, 'vendor_id')      AS vendor_id,
    JSONExtractString(after_json, 'name')           AS name,
    JSONExtractString(after_json, 'category')       AS category,
    JSONExtractString(after_json, '_id', '$oid')    AS mongo_id,
    event_time,
    op AS cdc_op
FROM raw.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'vendors';


-- Products
CREATE OR REPLACE VIEW sales.products_v AS
SELECT
    JSONExtractString(after_json, 'product_id')     AS product_id,
    JSONExtractString(after_json, 'name')           AS name,
    JSONExtractFloat(after_json,  'price')          AS price,
    JSONExtractString(after_json, '_id', '$oid')    AS mongo_id,
    event_time,
    op AS cdc_op
FROM raw.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'products';


-- Inventory
CREATE OR REPLACE VIEW sales.inventory_v AS
SELECT
    JSONExtractString(after_json, 'product_id')     AS product_id,
    JSONExtractInt(after_json,    'quantity')       AS quantity,
    JSONExtractString(after_json, '_id', '$oid')    AS mongo_id,
    event_time,
    op AS cdc_op
FROM raw.mongo_cdc_events
WHERE db = 'sales'
  AND collection = 'inventory';
