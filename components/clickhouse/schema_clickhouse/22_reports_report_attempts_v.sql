-- 22_reports_report_attempts_v.sql
-- Domain view for DAG nodes: report_attempts (Mongo -> CDC -> ClickHouse)

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.report_attempts_v AS
WITH
  after_json                                             AS j,

  -- started_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'started_at')                         AS start_raw,
  JSONExtractInt(start_raw, '$date')                      AS start_ms,
  JSONExtractString(j, 'started_at')                      AS start_str,
  if(
    start_ms != 0,
    toDateTime64(start_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(start_str)
  )                                                       AS started_at,

  -- ended_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'ended_at')                           AS end_raw,
  JSONExtractInt(end_raw, '$date')                        AS end_ms,
  JSONExtractString(j, 'ended_at')                        AS end_str,
  if(
    end_ms != 0,
    toDateTime64(end_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(end_str)
  )                                                       AS ended_at

SELECT
  -- identity
  JSONExtractString(j, '_id')                             AS _id,
  JSONExtractString(j, 'attempt_id')                      AS attempt_id,
  JSONExtractString(j, 'request_id')                      AS request_id,

  -- bridge back to your existing fact collection
  JSONExtractString(j, 'run_id')                          AS run_id,

  -- dims
  toInt32(ifNull(JSONExtractInt(j, 'attempt_no'), 0))      AS attempt_no,
  JSONExtractString(j, 'status')                          AS status,

  -- time
  started_at,
  ended_at,

  -- metrics
  toUInt32(ifNull(JSONExtractInt(j, 'latency_ms'), 0))     AS latency_ms,
  JSONExtractString(j, 'error_code')                      AS error_code,

  -- labels
  JSONExtract(j, 'tags', 'Array(String)')                 AS tags,

  -- CDC metadata
  ts_ms,
  event_time,
  op

FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'report_attempts'
  AND after_json != ''
  AND started_at IS NOT NULL;
