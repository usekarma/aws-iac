CREATE TABLE sales.events_timeline
(
    -- When the event actually happened (not when CH ingested it)
    event_time     DateTime64(3, 'UTC'),

    -- Where it came from
    source_system  LowCardinality(String),   -- 'mongo', 'servicenow', 'splunk', 'dynatrace', 'synthetic'
    source_type    LowCardinality(String),   -- 'cdc', 'log', 'alert', 'ticket', 'metric_agg', etc.

    -- What we’re talking about (for correlation)
    entity_type    LowCardinality(String),   -- 'order', 'customer', 'service', 'host', 'ticket'
    entity_id      String,                   -- order_id, customer_id, ticket_id, service name, etc.

    -- Optional “business key” for grouping a whole flow
    correlation_key String,                  -- e.g. order_id, quote_id, incident_id

    -- Event semantics
    event_name     LowCardinality(String),   -- 'order_created', 'order_updated', 'ticket_opened', 'alert_fired'
    severity       LowCardinality(String),   -- 'info','warn','error','critical' etc.
    status         LowCardinality(String),   -- 'open','closed','ack','resolved' (for tickets/alerts)

    message        String,                   -- human-ish summary for dashboards

    -- Technical correlation hooks (future: join to traces/logs)
    trace_id       String,
    span_id        String,

    -- Catch-all payload
    attributes     JSON,                     -- raw JSON with everything else
    ingest_time    DateTime64(3, 'UTC')      -- when CH saw it
)
ENGINE = MergeTree
PARTITION BY toDate(event_time)
ORDER BY (correlation_key, event_time, source_system, entity_type, entity_id);

CREATE TABLE sales.kafka_mongo_cdc_raw
(
    kafka_value String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'redpanda.svc.usekarma.local:9092',
    kafka_topic_list  = 'mongo-cdc-sales-orders',
    kafka_group_name  = 'ch-mongo-events-consumer',
    kafka_format      = 'JSONEachRow',
    kafka_num_consumers = 1;

CREATE MATERIALIZED VIEW sales.mv_mongo_orders_events
TO sales.events_timeline
AS
SELECT
    -- Use Debezium ts_ms as event time
    toDateTime64(JSONExtractInt(kafka_value, 'payload', 'ts_ms') / 1000.0, 3, 'UTC') AS event_time,

    'mongo' AS source_system,
    'cdc'   AS source_type,

    'order' AS entity_type,
    JSONExtractString(kafka_value, 'payload', 'after', 'order_id')   AS entity_id,

    -- In this POC, order_id is also the full “correlation key”
    JSONExtractString(kafka_value, 'payload', 'after', 'order_id')   AS correlation_key,

    -- Map Debezium op + order status into an event name
    CASE
        WHEN JSONExtractString(kafka_value, 'payload', 'op') = 'c'
            THEN 'order_created'
        WHEN JSONExtractString(kafka_value, 'payload', 'op') = 'u'
            THEN 'order_updated'
        WHEN JSONExtractString(kafka_value, 'payload', 'op') = 'd'
            THEN 'order_deleted'
        ELSE 'order_cdc'
    END AS event_name,

    'info' AS severity,
    concat('Mongo order ', event_name, ' for order_id=',
           JSONExtractString(kafka_value, 'payload', 'after', 'order_id')) AS message,

    -- No traces yet
    '' AS trace_id,
    '' AS span_id,

    -- Stuff the whole payload in attributes
    CAST(JSONExtract(kafka_value, 'payload', 'after', 'JSON'), 'JSON') AS attributes,

    now64(3) AS ingest_time
FROM sales.kafka_mongo_cdc_raw;

CREATE TABLE sales.stg_servicenow_tickets
(
    ticket_id        String,
    opened_at        DateTime64(3, 'UTC'),
    closed_at        Nullable(DateTime64(3, 'UTC')),
    short_description String,
    severity         String,
    correlation_key  String
)
ENGINE = MergeTree
ORDER BY ticket_id;

INSERT INTO sales.events_timeline
SELECT
    opened_at AS event_time,
    'servicenow' AS source_system,
    'ticket'     AS source_type,
    'ticket'     AS entity_type,
    ticket_id    AS entity_id,
    correlation_key,
    'ticket_opened' AS event_name,
    severity,
    'open'      AS status,
    short_description AS message,
    '' AS trace_id,
    '' AS span_id,
    CAST(map('ticket_id', ticket_id, 'short_description', short_description), 'JSON') AS attributes,
    now64(3) AS ingest_time
FROM sales.stg_servicenow_tickets;

CREATE TABLE sre.incident_candidates
ENGINE = ReplacingMergeTree
ORDER BY (correlation_key, first_seen_at) AS
SELECT
  correlation_key,
  min(event_time) AS first_seen_at,
  max(event_time) AS last_seen_at,
  countIf(source_system = 'dynatrace') AS num_dynatrace_alerts,
  countIf(source_system = 'splunk')    AS num_splunk_errors,
  anyIf(attributes, source_system = 'dynatrace') AS dynatrace_payload
FROM sales.events_timeline
WHERE severity IN ('error','critical')
GROUP BY correlation_key
HAVING
  num_dynatrace_alerts > 0 OR num_splunk_errors > 50;
