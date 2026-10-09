# Repository-local bounded agent workflow

Status: implementation for review. Human request: repo-specific Architect,
Builder, Verifier, Reviewer, Security and Operations contracts, one remediation
cycle, deterministic private evidence and IoT digital-twin example.

Scope: role Markdown, a Python stage runner, tests, example and documentation.
Preserve Terraform/Terragrunt components, config authority/compatibility, deployment
and planning/preflight scripts and CI. No AWS changes, cloud target selection,
plan, apply/destroy, certificate/secret work, state mutation, merges or pushes.
Use feature/bounded-agent-workflow. aws-config is read-only desired-state authority.

Design: consume supplied role reports and Git metadata; run only fixed repository
checks in a credential-isolated environment; record local/static results, explicit
absence of plan/live evidence and private logs. Stop for human after initial cycle;
allow one explicit remediation continuation within the identical request/scope,
re-run checks/reviews, then stop. No external AI APIs or shell hooks.

Verification: pinned Ruff, make verify/test, credential-free provider validation
for iot-digital-twin, integration run and tests for states, missing reviews,
failed gates, scope changes, remediation exhaustion, credential isolation and
no cloud/deployment command path. Evidence stays under ignored artifacts/ at
0700/0600. Failure to run gates is BLOCKED, never inferred success. Role reports
are supplied assessments, not independent attestation or AWS approval.

Rollback: revert repository changes; no AWS resources or data changed. A human
must confirm identity, exact environment/desired state, credentials and private
plan provenance before a separately scoped safe plan; concrete execution requires
separate reviewed approval. No live readiness claimed from this implementation.
