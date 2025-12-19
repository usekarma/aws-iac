-- 30_sla_report_runs.sql
-- SLA / Observability views for report generation pipeline

CREATE DATABASE IF NOT EXISTS sla;

-- Lifecycle metrics per run
CREATE OR REPLACE VIEW sla.report_runs_v AS
SELECT
    run_id,
    subscriber_id,
    report_type,
    status,

    requested_at,
    started_at,
    finished_at,

    -- Durations (seconds)
    dateDiff('second', requested_at, started_at)   AS queue_secs,
    dateDiff('second', started_at,   finished_at)  AS run_secs,
    dateDiff('second', requested_at, finished_at)  AS total_secs,

    -- Durations (milliseconds)
    dateDiff('millisecond', requested_at, started_at)  AS queue_ms,
    dateDiff('millisecond', started_at,   finished_at) AS run_ms,
    dateDiff('millisecond', requested_at, finished_at) AS total_ms

FROM reports.report_runs_v
WHERE requested_at IS NOT NULL
  AND finished_at IS NOT NULL;


-- Rolling 5-minute SLA window
CREATE OR REPLACE VIEW sla.report_runs_5m_v AS
SELECT
    window_start,
    count(*) AS total_runs,
    sum(total_secs <= 10) AS met_10s,
    sum(total_secs <= 30) AS met_30s,
    (sum(total_secs <= 10) / count()) * 100.0 AS pct_met_10s,
    (sum(total_secs <= 30) / count()) * 100.0 AS pct_met_30s
FROM
(
    SELECT
        run_id,
        total_secs,
        toStartOfFiveMinute(requested_at) AS window_start
    FROM sla.report_runs_v
)
GROUP BY window_start
ORDER BY window_start DESC;


-- SLA tier classification for each run
CREATE OR REPLACE VIEW sla.report_runs_tier_v AS
SELECT
    run_id,
    subscriber_id,
    report_type,
    total_secs,
    total_ms,

    multiIf(
        total_secs <= 10, 'Tier 1 (Excellent)',
        total_secs <= 30, 'Tier 2 (Good)',
        total_secs <= 60, 'Tier 3 (Slow)',
        'Tier 4 (Degraded)'
    ) AS sla_tier,

    requested_at,
    finished_at
FROM sla.report_runs_v;
