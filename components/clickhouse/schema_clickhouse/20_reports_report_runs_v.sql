-- 20_reports_report_runs_v.sql
-- Domain view for report execution lifecycle (Mongo -> CDC -> ClickHouse -> Grafana)

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.report_runs_v AS
WITH
  after_json                                            AS j,

  -- requested_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'requested_at')                      AS req_raw,
  JSONExtractInt(req_raw, '$date')                       AS req_ms,
  JSONExtractString(j, 'requested_at')                   AS req_str,
  if(
    req_ms != 0,
    toDateTime64(req_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(req_str)
  )                                                      AS requested_at,

  -- completed_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'completed_at')                      AS comp_raw,
  JSONExtractInt(comp_raw, '$date')                      AS comp_ms,
  JSONExtractString(j, 'completed_at')                   AS comp_str,
  if(
    comp_ms != 0,
    toDateTime64(comp_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(comp_str)
  )                                                      AS completed_at

SELECT
  -- identity
  JSONExtractString(j, '_id')                            AS _id,
  JSONExtractString(j, 'run_id')                         AS run_id,
  JSONExtractString(j, 'overlay_id')                     AS overlay_id,
  JSONExtractString(j, 'test_run_id')                    AS test_run_id,
  JSONExtractString(j, 'scenario_id')                    AS scenario_id,

  -- dims
  JSONExtractString(j, 'subscriber_id')                  AS subscriber_id,
  JSONExtractString(j, 'report_type')                    AS report_type,
  JSONExtractString(j, 'status')                         AS status,

  -- time
  requested_at,
  completed_at,

  -- metrics / labels
  toUInt32(ifNull(JSONExtractInt(j, 'latency_ms'), 0))    AS latency_ms,
  JSONExtractString(j, 'dependency')                     AS dependency,
  JSONExtractString(j, 'error_code')                     AS error_code,
  JSONExtractString(j, 'incident_id')                    AS incident_id,
  JSONExtract(j, 'tags', 'Array(String)')                AS tags,

  -- CDC metadata
  ts_ms,
  event_time,
  op

FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'report_runs'
  AND after_json != ''
  AND requested_at IS NOT NULL;
