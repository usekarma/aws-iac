-- 40_reports_dag_edges_v.sql
-- Materialized "edges" view for a meaningful DAG (Grafana-friendly)
--
-- Emits one row per edge with optional latency.
-- This is intentionally a *view* (not a table) to keep PoC wiring simple.

CREATE DATABASE IF NOT EXISTS reports;

CREATE OR REPLACE VIEW reports.dag_edges_v AS
WITH
  -- Keep a single 'time' field for Grafana time-series compatibility
  -- Prefer requested_at for request-root edges; started_at for attempt edges.
  1 AS _dummy
SELECT
  -- time
  rq.requested_at                                         AS time,

  -- edge identity
  rq.request_id                                           AS request_id,
  'REQUEST'                                               AS src_type,
  rq.request_id                                           AS src_id,
  'ATTEMPT'                                               AS dst_type,
  at.attempt_id                                           AS dst_id,
  'REQUEST_TO_ATTEMPT'                                    AS edge_type,

  -- optional measures
  toUInt32(0)                                             AS latency_ms,
  ''                                                      AS dep,
  ''                                                      AS status,
  at.run_id                                               AS run_id,
  at.attempt_no                                           AS attempt_no
FROM reports.report_requests_v rq
INNER JOIN reports.report_attempts_v at
  ON at.request_id = rq.request_id

UNION ALL

SELECT
  -- time
  at.started_at                                           AS time,

  -- edge identity
  at.request_id                                           AS request_id,
  'ATTEMPT'                                               AS src_type,
  at.attempt_id                                           AS src_id,
  'DEPENDENCY_CALL'                                       AS dst_type,
  dc.call_id                                              AS dst_id,
  'ATTEMPT_TO_DEPENDENCY'                                 AS edge_type,

  -- optional measures
  dc.latency_ms                                           AS latency_ms,
  dc.dep                                                  AS dep,
  dc.status                                               AS status,
  at.run_id                                               AS run_id,
  at.attempt_no                                           AS attempt_no
FROM reports.report_attempts_v at
INNER JOIN reports.dependency_calls_v dc
  ON dc.attempt_id = at.attempt_id

UNION ALL

SELECT
  -- time (use decided_at so outcomes show up even if requested_at parsing differs)
  oc.decided_at                                           AS time,

  -- edge identity
  oc.request_id                                           AS request_id,
  'REQUEST'                                               AS src_type,
  oc.request_id                                           AS src_id,
  'OUTCOME'                                               AS dst_type,
  oc.request_id                                           AS dst_id,   -- outcome node can key off request_id in PoC
  'REQUEST_TO_OUTCOME'                                    AS edge_type,

  -- optional measures
  oc.final_latency_ms                                     AS latency_ms,
  oc.breach_reason                                        AS dep,
  oc.final_status                                         AS status,
  ''                                                      AS run_id,
  toInt32(0)                                              AS attempt_no
FROM reports.outcomes_v oc

UNION ALL

-- Retry edges: attempt N -> attempt N+1 (requires attempt_no)
SELECT
  a1.started_at                                           AS time,
  a1.request_id                                           AS request_id,
  'ATTEMPT'                                               AS src_type,
  a1.attempt_id                                           AS src_id,
  'ATTEMPT'                                               AS dst_type,
  a2.attempt_id                                           AS dst_id,
  'ATTEMPT_RETRY'                                         AS edge_type,
  toUInt32(0)                                             AS latency_ms,
  ''                                                      AS dep,
  ''                                                      AS status,
  a2.run_id                                               AS run_id,
  a2.attempt_no                                           AS attempt_no
FROM reports.report_attempts_v a1
INNER JOIN reports.report_attempts_v a2
  ON a2.request_id = a1.request_id AND a2.attempt_no = a1.attempt_no + 1;
