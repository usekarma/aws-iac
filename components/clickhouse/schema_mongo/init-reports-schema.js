// ================================================
// MongoDB Reports Schema Bootstrap (Idempotent, Permissive)
// ================================================
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" init-reports-schema.js
//
// Behavior:
//   - Creates database "reports" if missing
//   - Ensures "report_runs" collection exists
//   - Clears any validator (no validation errors for PoC)
//   - Resets indexes and adds non-unique ones for common query patterns
//   - Optional: if RESET_REPORTS_DB=true (env), truncates collection
// ================================================

(function () {
  print("\n=== Initializing MongoDB schema for REPORTS ===\n");

  const dbName = "reports";
  const reportsDb = db.getSiblingDB(dbName);

  // Optional destructive reset for demos:
  // Set environment variable RESET_REPORTS_DB=true to clear data.
  const resetEnv =
    (typeof process !== "undefined" &&
      process.env &&
      process.env.RESET_REPORTS_DB) ||
    "";
  const resetReportsDb = (resetEnv || "").toLowerCase() === "true";

  if (resetReportsDb) {
    print("⚠️  RESET_REPORTS_DB=true detected — dropping existing 'report_runs' collection (if it exists)...");
    reportsDb.report_runs.drop();
  }

  // -------------------------------
  // Ensure collection exists
  // -------------------------------
  const existingCollections = reportsDb.getCollectionNames();
  const hasReportRuns = existingCollections.indexOf("report_runs") !== -1;

  if (!hasReportRuns) {
    print("Creating 'report_runs' collection with NO validator (permissive for PoC)...");
    reportsDb.createCollection("report_runs");
  } else {
    print("'report_runs' collection already exists.");
  }

  // At this point collection exists; get a handle
  const reportRuns = reportsDb.getCollection("report_runs");

  // -------------------------------
  // Clear any existing validator
  // -------------------------------
  print("Clearing any existing validator on 'report_runs' (making schema permissive for PoC)...");

  reportsDb.runCommand({
    collMod: "report_runs",
    validator: {},         // no validation rules
    validationLevel: "off" // extra safety
  });

  // -------------------------------
  // Reset indexes to avoid conflicts
  // -------------------------------
  print("Dropping existing indexes on 'report_runs' (if any)...");
  try {
    reportRuns.dropIndexes();
  } catch (e) {
    // ignore if none exist
  }

  // -------------------------------
  // Indexes (idempotent, NON-UNIQUE)
  // -------------------------------
  print("Ensuring indexes on 'report_runs'...");

  // run_id index (NOT unique, to avoid dup-key pain)
  reportRuns.createIndex(
    { run_id: 1 },
    { name: "ix_run_id" }
  );

  // Subscriber + time (for per-subscriber timelines)
  reportRuns.createIndex(
    { subscriber_id: 1, requested_at: -1 },
    { name: "ix_subscriber_requested_at" }
  );

  // Status + time (for dashboards like “recent failures”)
  reportRuns.createIndex(
    { status: 1, requested_at: -1 },
    { name: "ix_status_requested_at" }
  );

  // Report type + window (for aggregations by type)
  reportRuns.createIndex(
    { report_type: 1, requested_at: -1 },
    { name: "ix_report_type_requested_at" }
  );

  print("\n✅ Reports schema bootstrap complete.");
  if (resetReportsDb) {
    print("⚠️ 'report_runs' was cleared due to RESET_REPORTS_DB=true.\n");
  } else {
    print("   Existing data (if any) was preserved.\n");
  }
})();
