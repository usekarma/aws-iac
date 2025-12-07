-- 20_reports_report_runs_v.sql
-- Domain view for report execution lifecycle

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.report_runs_v AS
SELECT
    JSONExtractString(after_json, 'run_id')            AS run_id,
    JSONExtractString(after_json, 'subscriber_id')     AS subscriber_id,
    JSONExtractString(after_json, 'report_type')       AS report_type,
    JSONExtractString(after_json, 'status')            AS status,
    JSONExtractString(after_json, 'error_code')        AS error_code,
    JSONExtractString(after_json, 'error_message')     AS error_message,
    JSONExtractString(after_json, '_id', '$oid')       AS mongo_id,

    -- Timestamps (strings in Mongo)
    parseDateTimeBestEffortOrNull(JSONExtractString(after_json, 'requested_at'))  AS requested_at,
    parseDateTimeBestEffortOrNull(JSONExtractString(after_json, 'started_at'))    AS started_at,
    parseDateTimeBestEffortOrNull(JSONExtractString(after_json, 'completed_at'))  AS completed_at,

    event_time,
    op AS cdc_op
FROM raw.mongo_cdc_events
WHERE db = 'reports'
  AND collection = 'report_runs';
