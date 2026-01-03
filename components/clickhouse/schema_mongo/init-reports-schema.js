// ================================================
// MongoDB Reports Schema Bootstrap (Idempotent, Permissive)
// ================================================
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" init-reports-schema.js
//
// Behavior:
//   - Creates database "reports" if missing
//   - Ensures collections exist (report_runs + DAG collections)
//   - Clears any validators (no validation errors for PoC)
//   - Resets indexes and adds non-unique ones for common query patterns
//   - Optional destructive reset for demos:
//       RESET_REPORTS_DB=true  -> drops *all* reports collections
//       RESET_REPORTS_DB=soft  -> deletes documents from all reports collections
//
// Collections created:
//   - report_runs        : flattened execution facts (existing)
//   - report_requests    : one doc per logical request (DAG root)
//   - report_attempts    : one doc per attempt/retry (DAG nodes)
//   - dependency_calls   : one doc per downstream call (DAG fan-out)
//   - outcomes           : one doc per request, final truth record
// ================================================

(function () {
  print("\n=== Initializing MongoDB schema for REPORTS (with DAG collections) ===\n");

  const dbName = "reports";
  const reportsDb = db.getSiblingDB(dbName);

  // ------------------------------------------------
  // Reset behavior (optional, for demos)
  // ------------------------------------------------
  const resetEnv =
    (typeof process !== "undefined" &&
      process.env &&
      process.env.RESET_REPORTS_DB) ||
    "";
  const resetMode = (resetEnv || "").toLowerCase(); // "true" | "soft" | ""

  const COLLS = [
    "report_runs",
    "report_requests",
    "report_attempts",
    "dependency_calls",
    "outcomes"
  ];

  function dropAllCollections() {
    COLLS.forEach((c) => {
      try {
        print(`⚠️  Dropping collection '${c}' (if it exists)...`);
        reportsDb.getCollection(c).drop();
      } catch (e) {
        // ignore
      }
    });
  }

  function clearAllCollections() {
    COLLS.forEach((c) => {
      try {
        print(`⚠️  Clearing documents from '${c}'...`);
        reportsDb.getCollection(c).deleteMany({});
      } catch (e) {
        // ignore
      }
    });
  }

  if (resetMode === "true") {
    print("⚠️  RESET_REPORTS_DB=true detected — dropping ALL reports collections...");
    dropAllCollections();
  } else if (resetMode === "soft") {
    print("⚠️  RESET_REPORTS_DB=soft detected — deleting ALL documents (keeping collections/indexes)...");
    clearAllCollections();
  }

  // ------------------------------------------------
  // Helpers
  // ------------------------------------------------
  function ensureCollection(name) {
    const existing = reportsDb.getCollectionNames();
    const has = existing.indexOf(name) !== -1;
    if (!has) {
      print(`Creating '${name}' collection with NO validator (permissive for PoC)...`);
      reportsDb.createCollection(name);
    } else {
      print(`'${name}' collection already exists.`);
    }

    // Clear any existing validator to avoid PoC pain
    print(`Clearing any existing validator on '${name}' (making schema permissive for PoC)...`);
    reportsDb.runCommand({
      collMod: name,
      validator: {},
      validationLevel: "off"
    });

    return reportsDb.getCollection(name);
  }

  function resetIndexes(coll, name) {
    print(`Dropping existing indexes on '${name}' (if any)...`);
    try {
      coll.dropIndexes();
    } catch (e) {
      // ignore if none exist
    }
  }

  // ------------------------------------------------
  // 1) report_runs (existing)
  // ------------------------------------------------
  const reportRuns = ensureCollection("report_runs");
  resetIndexes(reportRuns, "report_runs");

  print("Ensuring indexes on 'report_runs'...");

  // run_id index (NOT unique, to avoid dup-key pain)
  reportRuns.createIndex({ run_id: 1 }, { name: "ix_run_id" });

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

  // Optional helper: request_id (if/when you add it to report_runs)
  reportRuns.createIndex(
    { request_id: 1, requested_at: -1 },
    { name: "ix_request_id_requested_at" }
  );

  // ------------------------------------------------
  // 2) report_requests (DAG root)
  // ------------------------------------------------
  const reportRequests = ensureCollection("report_requests");
  resetIndexes(reportRequests, "report_requests");

  print("Ensuring indexes on 'report_requests'...");
  reportRequests.createIndex({ request_id: 1 }, { name: "ix_request_id", unique: true });
  reportRequests.createIndex({ requested_at: -1 }, { name: "ix_requested_at" });
  reportRequests.createIndex(
    { subscriber_id: 1, requested_at: -1 },
    { name: "ix_req_subscriber_requested_at" }
  );
  reportRequests.createIndex(
    { report_type: 1, requested_at: -1 },
    { name: "ix_req_report_type_requested_at" }
  );

  // ------------------------------------------------
  // 3) report_attempts (DAG nodes)
  // ------------------------------------------------
  const reportAttempts = ensureCollection("report_attempts");
  resetIndexes(reportAttempts, "report_attempts");

  print("Ensuring indexes on 'report_attempts'...");
  reportAttempts.createIndex({ attempt_id: 1 }, { name: "ix_attempt_id", unique: true });
  reportAttempts.createIndex({ request_id: 1 }, { name: "ix_att_request_id" });
  reportAttempts.createIndex(
    { request_id: 1, attempt_no: 1 },
    { name: "ix_att_request_attempt_no" }
  );
  // Bridge back to your existing flattened facts
  reportAttempts.createIndex({ run_id: 1 }, { name: "ix_att_run_id" });
  reportAttempts.createIndex({ started_at: -1 }, { name: "ix_att_started_at" });

  // ------------------------------------------------
  // 4) dependency_calls (fan-out)
  // ------------------------------------------------
  const depCalls = ensureCollection("dependency_calls");
  resetIndexes(depCalls, "dependency_calls");

  print("Ensuring indexes on 'dependency_calls'...");
  depCalls.createIndex({ attempt_id: 1 }, { name: "ix_dep_attempt_id" });
  depCalls.createIndex(
    { dep: 1, started_at: -1 },
    { name: "ix_dep_name_started_at" }
  );
  depCalls.createIndex(
    { status: 1, started_at: -1 },
    { name: "ix_dep_status_started_at" }
  );

  // ------------------------------------------------
  // 5) outcomes (terminal truth record)
  // ------------------------------------------------
  const outcomes = ensureCollection("outcomes");
  resetIndexes(outcomes, "outcomes");

  print("Ensuring indexes on 'outcomes'...");
  outcomes.createIndex({ request_id: 1 }, { name: "ix_out_request_id", unique: true });
  outcomes.createIndex({ decided_at: -1 }, { name: "ix_out_decided_at" });
  outcomes.createIndex(
    { final_status: 1, decided_at: -1 },
    { name: "ix_out_status_decided_at" }
  );
  outcomes.createIndex(
    { breach_reason: 1, decided_at: -1 },
    { name: "ix_out_breach_reason_decided_at" }
  );

  // ------------------------------------------------
  // Done
  // ------------------------------------------------
  print("\n✅ Reports schema bootstrap complete (report_runs + DAG collections).");
  if (resetMode === "true") {
    print("⚠️  All reports collections were dropped due to RESET_REPORTS_DB=true.\n");
  } else if (resetMode === "soft") {
    print("⚠️  All documents were deleted due to RESET_REPORTS_DB=soft.\n");
  } else {
    print("   Existing data (if any) was preserved.\n");
  }
})();
