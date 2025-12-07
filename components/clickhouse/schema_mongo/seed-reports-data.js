// ================================================
// MongoDB Reports Traffic Seeder (mongosh)
// ================================================
// Usage:
//   REPORT_SEED_HOURS=6 REPORT_RUNS_PER_HOUR=120 \
//   mongosh "mongodb://127.0.0.1:27017" generate-report-traffic.js
//
// Behavior:
//   - Seeds historical report_runs over the last N hours
//   - Varies latency by subscriber tier (enterprise/pro/free)
//   - Injects failures and slow (SLA-violating) runs
// ================================================

(function () {
  print("\n=== Seeding MongoDB REPORTS traffic for SLA demo ===\n");

  const dbName = "reports";
  const reportsDb = db.getSiblingDB(dbName);
  const coll = reportsDb.getCollection("report_runs");

  // Config from env or defaults
  const HOURS = parseInt((typeof process !== "undefined" && process.env && process.env.REPORT_SEED_HOURS) || "6", 10);
  const RUNS_PER_HOUR = parseInt((typeof process !== "undefined" && process.env && process.env.REPORT_RUNS_PER_HOUR) || "120", 10);

  const totalRuns = HOURS * RUNS_PER_HOUR;

  print(`Seeding approx ${totalRuns} runs over last ${HOURS} hour(s)…`);

  const REPORT_TYPES = ["daily_summary", "inventory_delta", "risk_scoring", "fraud_watch", "activity_digest"];

  const SUBSCRIBERS = [
    { id: "A100", tier: "enterprise" },
    { id: "B200", tier: "pro" },
    { id: "C300", tier: "pro" },
    { id: "D400", tier: "free" },
    { id: "E500", tier: "free" }
  ];

  function pickRandom(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function simulateLatencyMs(tier) {
    if (tier === "enterprise") return Math.floor(200 + Math.random() * 300);   // 0.2–0.5s
    if (tier === "pro")        return Math.floor(300 + Math.random() * 700);   // 0.3–1.0s
    return Math.floor(500 + Math.random() * 4000);                             // 0.5–5.0s
  }

  function maybeOutlierMs(latencyMs) {
    // 5% of runs are nasty outliers
    if (Math.random() < 0.05) {
      return latencyMs + (3000 + Math.random() * 8000); // +3–11s
    }
    return latencyMs;
  }

  function maybeFailure() {
    if (Math.random() < 0.10) {
      const errors = [
        { code: "TIMEOUT",        msg: "Execution exceeded SLA timeout." },
        { code: "UPSTREAM_ERROR", msg: "Dependency service returned 500." },
        { code: "MISSING_DATA",   msg: "Required dataset unavailable." }
      ];
      return pickRandom(errors);
    }
    return null;
  }

  // Helper for unique run IDs (string, never null)
  function newRunId() {
    return new ObjectId().toString(); // unique, string; works with unique index
  }

  const now = new Date();
  const msPerHour = 60 * 60 * 1000;
  const startWindow = new Date(now.getTime() - HOURS * msPerHour);

  const bulk = coll.initializeUnorderedBulkOp();

  for (let i = 0; i < totalRuns; i++) {
    const subscriber = pickRandom(SUBSCRIBERS);
    const tier = subscriber.tier;
    const reportType = pickRandom(REPORT_TYPES);

    // Random requested_at within [startWindow, now]
    const offsetMs = Math.random() * (now.getTime() - startWindow.getTime());
    const requestedAt = new Date(startWindow.getTime() + offsetMs);

    // Split total latency into queue + run
    let baseLatencyMs = simulateLatencyMs(tier);
    baseLatencyMs = maybeOutlierMs(baseLatencyMs);

    // Randomly allocate between queue and run portions
    const queueFraction = 0.2 + Math.random() * 0.4; // 20–60% waiting
    const queueMs = Math.floor(baseLatencyMs * queueFraction);
    const runMs = baseLatencyMs - queueMs;

    const startedAt = new Date(requestedAt.getTime() + queueMs);
    const completedAt = new Date(startedAt.getTime() + runMs);

    const failure = maybeFailure();

    const doc = {
      run_id: newRunId(),                 // ✅ string, non-null
      subscriber_id: subscriber.id,
      report_type: reportType,

      requested_at: requestedAt,
      started_at: startedAt,
      completed_at: completedAt,

      status: failure ? "failed" : "completed",
      error_code: failure ? failure.code : null,
      error_message: failure ? failure.msg : null
    };

    bulk.insert(doc);

    if (i > 0 && i % 1000 === 0) {
      print(`  queued ${i} runs…`);
    }
  }

  if (totalRuns > 0) {
    const res = bulk.execute();
    printjson(res);
  }

  print("\n✅ Reports traffic seeding complete.\n");
})();
