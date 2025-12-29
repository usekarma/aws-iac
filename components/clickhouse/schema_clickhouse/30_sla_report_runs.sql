-- 30_sla_report_runs.sql
-- SLA / Observability views for report generation pipeline

CREATE DATABASE IF NOT EXISTS sla;

CREATE OR REPLACE VIEW sla.report_runs_v AS
SELECT
  run_id,
  subscriber_id,
  report_type,
  status,

  requested_at,
  completed_at,

  -- total duration
  dateDiff('second', requested_at, completed_at)      AS total_secs,
  dateDiff('millisecond', requested_at, completed_at) AS total_ms,

  -- use generator-provided latency_ms when present
  latency_ms
FROM reports.report_runs_v
WHERE requested_at IS NOT NULL
  AND completed_at IS NOT NULL;
