-- 20_reports_report_runs_v.sql
-- Domain view for report execution lifecycle (Mongo -> CDC -> ClickHouse -> Grafana)

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.report_runs_v AS
SELECT
  JSONExtractString(after_json, 'run_id')        AS run_id,
  JSONExtractString(after_json, 'subscriber_id') AS subscriber_id,
  JSONExtractString(after_json, 'report_type')   AS report_type,
  JSONExtractString(after_json, 'status')        AS status,
  JSONExtractString(after_json, 'stage')         AS stage,
  JSONExtractString(after_json, 'incident')      AS incident,

  JSONExtractString(after_json, 'error_code')    AS error_code,
  JSONExtractString(after_json, 'error_message') AS error_message,
  JSONExtractString(after_json, '_id', '$oid')   AS mongo_id,

  -- requested_at
  coalesce(
    if(
      JSONExtractInt(after_json, 'requested_at', '$date') IS NULL,
      NULL,
      fromUnixTimestamp64Milli(
        JSONExtractInt(after_json, 'requested_at', '$date')
      )
    ),
    parseDateTime64BestEffortOrNull(
      JSONExtractString(after_json, 'requested_at')
    )
  ) AS requested_at,

  -- started_at
  coalesce(
    if(
      JSONExtractInt(after_json, 'started_at', '$date') IS NULL,
      NULL,
      fromUnixTimestamp64Milli(
        JSONExtractInt(after_json, 'started_at', '$date')
      )
    ),
    parseDateTime64BestEffortOrNull(
      JSONExtractString(after_json, 'started_at')
    )
  ) AS started_at,

  -- finished_at (preferred) or completed_at (legacy)
  coalesce(
    if(
      JSONExtractInt(after_json, 'finished_at', '$date') IS NULL,
      NULL,
      fromUnixTimestamp64Milli(
        JSONExtractInt(after_json, 'finished_at', '$date')
      )
    ),
    parseDateTime64BestEffortOrNull(
      JSONExtractString(after_json, 'finished_at')
    ),
    if(
      JSONExtractInt(after_json, 'completed_at', '$date') IS NULL,
      NULL,
      fromUnixTimestamp64Milli(
        JSONExtractInt(after_json, 'completed_at', '$date')
      )
    ),
    parseDateTime64BestEffortOrNull(
      JSONExtractString(after_json, 'completed_at')
    )
  ) AS finished_at,

  -- updated_at
  coalesce(
    if(
      JSONExtractInt(after_json, 'updated_at', '$date') IS NULL,
      NULL,
      fromUnixTimestamp64Milli(
        JSONExtractInt(after_json, 'updated_at', '$date')
      )
    ),
    parseDateTime64BestEffortOrNull(
      JSONExtractString(after_json, 'updated_at')
    )
  ) AS updated_at,

  event_time,
  op AS cdc_op

FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'report_runs'
  AND length(after_json) > 0;
