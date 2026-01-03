-- 21_reports_report_requests_v.sql
-- Domain view for DAG root: report_requests (Mongo -> CDC -> ClickHouse)

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.report_requests_v AS
WITH
  after_json                                             AS j,

  -- requested_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'requested_at')                       AS req_raw,
  JSONExtractInt(req_raw, '$date')                        AS req_ms,
  JSONExtractString(j, 'requested_at')                    AS req_str,
  if(
    req_ms != 0,
    toDateTime64(req_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(req_str)
  )                                                       AS requested_at

SELECT
  -- identity
  JSONExtractString(j, '_id')                             AS _id,
  JSONExtractString(j, 'request_id')                      AS request_id,

  -- dims
  JSONExtractString(j, 'subscriber_id')                   AS subscriber_id,
  JSONExtractString(j, 'report_type')                     AS report_type,

  -- time
  requested_at,

  -- SLA config (optional, but useful)
  toUInt32(ifNull(JSONExtractInt(j, 'sla_ms'), 0))         AS sla_ms,
  JSONExtractString(j, 'priority')                        AS priority,

  -- labels
  JSONExtract(j, 'tags', 'Array(String)')                 AS tags,

  -- CDC metadata
  ts_ms,
  event_time,
  op

FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'report_requests'
  AND after_json != ''
  AND requested_at IS NOT NULL;
