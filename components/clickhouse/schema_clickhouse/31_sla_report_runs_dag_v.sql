-- 31_sla_report_runs_dag_v.sql
-- SLA view augmented with DAG linkage (request_id/attempt_id) WITHOUT changing existing sla.report_runs_v
--
-- Use this for "click a breach -> open DAG drilldown" wiring in Grafana.

CREATE DATABASE IF NOT EXISTS sla;

CREATE OR REPLACE VIEW sla.report_runs_dag_v AS
SELECT
  s.run_id,
  s.subscriber_id,
  s.report_type,
  s.status,

  s.requested_at,
  s.completed_at,

  s.total_secs,
  s.total_ms,
  s.latency_ms,

  -- DAG linkage (preferred)
  a.request_id,
  a.attempt_id,
  a.attempt_no

FROM sla.report_runs_v s
LEFT JOIN reports.report_attempts_v a
  ON a.run_id = s.run_id;
