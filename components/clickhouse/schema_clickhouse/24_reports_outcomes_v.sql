-- 24_reports_outcomes_v.sql
-- Domain view for request terminal truth: outcomes (Mongo -> CDC -> ClickHouse)

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.outcomes_v AS
WITH
  after_json                                             AS j,

  -- decided_at: supports either ISO string or {"$date":ms}
  JSONExtractRaw(j, 'decided_at')                         AS dec_raw,
  JSONExtractInt(dec_raw, '$date')                        AS dec_ms,
  JSONExtractString(j, 'decided_at')                      AS dec_str,
  if(
    dec_ms != 0,
    toDateTime64(dec_ms / 1000.0, 3, 'UTC'),
    parseDateTime64BestEffortOrNull(dec_str)
  )                                                       AS decided_at

SELECT
  -- identity
  JSONExtractString(j, '_id')                             AS _id,
  JSONExtractString(j, 'request_id')                      AS request_id,

  -- result
  JSONExtractString(j, 'final_status')                    AS final_status,
  toUInt32(ifNull(JSONExtractInt(j, 'final_latency_ms'), 0)) AS final_latency_ms,
  JSONExtractString(j, 'breach_reason')                   AS breach_reason,

  -- time
  decided_at,

  -- CDC metadata
  ts_ms,
  event_time,
  op

FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'outcomes'
  AND after_json != ''
  AND decided_at IS NOT NULL;
