# Bounded repository role workflow

The six [.agent contracts](../.agent/README.md) make aws-iac a local participant in
an agent-assisted engineering process. aws-config remains desired-state authority.
This v1 is a stage/evidence runner, not an LLM runtime: it does not generate code,
invoke external AI APIs, run arbitrary request commands or deploy infrastructure.
People/assisted sessions implement and supply semantic reviews before each run.
Read AGENTS.md and inspect gate scripts before executing repository code.

```text
human work request and supplied Architect/Builder reports
  → Architect → Builder → Verifier (fixed local gates)
  → Reviewer → Security → Operations (supplied assessments)
  → READY_FOR_HUMAN_REVIEW or BLOCKED → STOP_FOR_HUMAN
if BLOCKED: one explicit repository remediation and fresh reports
  → re-run all verification and reviews → final state → STOP_FOR_HUMAN
```

`READY_FOR_HUMAN_REVIEW` means local gates and supplied assessments contain no
blockers. It is not approval, independently attested semantic review, a live plan
or production readiness. Unknown risk flags and human decisions stay explicit.
Missing assessments, incomplete Builder work, failed/missing gates, unauthorized
files or changing source snapshots make the report BLOCKED. One continuation is
allowed per evidence directory; another fails without running gates. New scope
or changed desired-state revision requires a new human-reviewed work request,
not laundering the same failed run as an automatic fresh cycle.

## Input and execution

Use [the IoT request example](../examples/agent-workflow-iot.json). Required fields:
identifier, affected components, explicit desired-state repository/config paths,
human authorization reference, allowed repository paths, Architect plan/risks/
assumptions/decisions, Builder completion/summary, and Reviewer/Security/Operations
summaries/findings/blockers. Allowed paths ending in `/` authorize that directory;
others authorize exact files. Unknown fields (including commands, profiles and
approval flags) are rejected. References/role reports are supplied context and
cannot grant AWS authority. Never include credentials or secret/runtime values.

The runner fingerprints Git commits, declared desired-state files, compatibility
manifest and changed file contents (including untracked, excluding ignored).
Changes since VERIFY_BASE_REF (default origin/main) plus local WIP form the review
scope. Choose the genuine comparison base; never move it to hide unrelated edits.
All findings/results are bound to that observed snapshot. Concurrent source edits
block readiness. Reviewers must refresh their reports after implementation changes;
the runner cannot attest when a human actually reviewed a diff.

```bash
export AGENT_MODE=1
python3 scripts/agent_workflow.py /PRIVATE/work-request.json
# After an initial BLOCKED run, one authorized repository fix pass and fresh reports:
python3 scripts/agent_workflow.py /PRIVATE/work-request.json --remediate
```

Default output: `artifacts/agent-workflow/<request-id>/cycle-0/`; remediation uses
`cycle-1/` and preserves cycle-0. `--output` may choose a new directory only under
ignored `artifacts/agent-workflow/`. Directories/files use 0700/0600. Each cycle has
request.json, evidence.json, report.md, private gate logs and a SHA-256 manifest.
No plan/state/runtime output is committed or copied into public documentation.
JSON records gates/results, source/diff fingerprints, risk flags, findings,
blockers, decisions, transitions and final status. Summaries omit gate stdout;
logs can still be sensitive and are private. No artifact upload is added to CI.
Identical inputs, snapshots and gate outcomes yield identical summary JSON/Markdown;
log timing/provider diagnostics can differ. Hashes establish integrity, not provenance
or human approval. Exit 0: ready for human review; 2: completed but blocked;
1: invalid source/request, integrity/timeout infrastructure failure or exhausted run.
Gate timeouts are recorded as ERROR/blockers. No automatic retry or remediation.

## Deterministic gates and authority

Fixed commands, never taken from request text:

- `python scripts/check_config_contract.py --aws-config-dir <explicit source>`.
- `bash scripts/verify.sh --terraform COMPONENT` for each affected module. This
  existing path includes formatting/lint, JSON, tests, static security regressions,
  Terraform fmt and Terragrunt HCL validation, then disposable provider validation
  with init -backend=false. The runner does not add redundant standalone verify
  or make test calls. Multi-component runs repeat the supported combined gate per
  component; no internal provider-validation logic is copied into the runner.

A temporary HOME and explicit empty AWS credential/config locations isolate local
gates. No inherited AWS profile, credentials, mutation acknowledgement, Terraform
CLI overrides, backend bootstrap flags or auth hooks are passed. AGENT_MODE=1 is
forced. Config test source is passed through AWS_CONFIG_DIR; existing CI's nested
aws-config checkout remains the default when that variable is absent. Use the
hash-pinned verification tools; registry access may be needed for providers, not
AWS credentials. Missing source or failed provider downloads block readiness.
Repository gate code itself must remain trusted/reviewed; isolation is not an OS
sandbox or a replacement for read-only IAM.

No AWS account is selected. The runner has no live planning, preflight, apply,
destroy, certificate/secret, backend/state, merge or push entrypoint. It never
uses AWS_MUTATION_APPROVED as evidence of authorization and does not modify the
existing deploy.sh, plan.sh, preflight.sh, config compatibility or CI behavior.

Evidence explicitly states local/static checks, plan NOT_PRODUCED and live AWS
NOT_COLLECTED. Before a separately requested live plan, a human must independently
confirm profile/account/region/environment/binding and desired-state revision,
provide suitable read-only credentials, and verify STS/preflight. The verifier
then uses existing scripts/plan.sh and private scripts/evidence.py artifacts.
No auto-approve or backend bootstrap. Before deployment, review the exact current
saved plan, resource/data/security/cost risks, backups/restore evidence and obtain
separate approval for the concrete AWS operation. Environment variables or this
runner's final status cannot supply that approval.

## Local gate setup

Use the existing virtualenv and hash-locked development tools; `shellcheck_py`
in `requirements-dev.lock` supplies ShellCheck, so no global installation is needed.
Standalone gates need the same explicit config checkout that the runner passes:

```bash
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
export AGENT_MODE=1
export AWS_CONFIG_DIR=../aws-config
bash scripts/verify.sh
make test
python scripts/check_config_contract.py --aws-config-dir ../aws-config
bash scripts/verify.sh --terraform iot-digital-twin
```

The IoT contract test resolves relative `AWS_CONFIG_DIR` paths from the aws-iac
repository root. Without that variable it retains CI's nested `aws-config/`
checkout. Empty or missing explicit checkouts fail; no sibling/path search occurs.
The compatibility CLI still requires its own explicit `--aws-config-dir` argument.

## Concrete IoT digital-twin review

1. Inspect `../aws-config/iac/dev/iot-digital-twin/core2-aws-001/config.json`, the
   compatibility contract and `components/iot-digital-twin/`. Confirm certificate
   authority, device_id as data, principal/topic trust and server replay/stale
   enforcement. Do not infer an AWS account from the dev nickname.
2. Copy the example into a private request; replace authorization reference and
   allowed paths with the actual approved request. The shipped example deliberately
   has incomplete Builder work and blocking placeholder reviews, so cannot claim
   readiness. Fill reports only after real inspection/authorized repository edits.
3. Run `python3 scripts/agent_workflow.py /PRIVATE/iot-request.json`. Review
   every gate and DynamoDB retention/PITR/TTL, logging, costs and recovery.
   Certificate issuance and deferred TwinMaker support are explicit human decisions;
   a clean local gate does not implement missing integrations.
4. If blocked, fix only authorized repository findings once, update all role
   assessments, and use `--remediate`. Remaining blockers stay BLOCKED. Stop for
   human in either case. No IoT certificates, secrets or AWS resources are created.


## Evaluate an existing component without implementing it

Evaluation is a separate CLI mode with no Builder report, authorized-edit scope,
or remediation transition:

```bash
AGENT_MODE=1 python3 scripts/agent_workflow.py --evaluate iot-digital-twin \
  --aws-config-dir ../aws-config \
  --config-path iac/dev/iot-digital-twin/core2-aws-001/config.json \
  --assessment /PRIVATE/iot-assessment.json \
  --output artifacts/agent-workflow/evaluate-iot-UNIQUE

AGENT_MODE=1 python3 scripts/agent_workflow.py --evaluate clickhouse \
  --aws-config-dir ../aws-config \
  --config-path iac/prod/clickhouse/usekarma-dev/config.json \
  --assessment /PRIVATE/clickhouse-assessment.json \
  --output artifacts/agent-workflow/evaluate-clickhouse-UNIQUE
```

The explicit prod config path is a source reference, not production account/profile
selection. No target credentials or live preflight/plan are invoked. `--assessment`
accepts only `architect` and `reviews` in the same format as implementation requests.
Supply actual component findings, including security, cost, persistent data,
destructive/replacement unknowns, blockers and decisions. Without an assessment,
missing semantic reviews are blockers; the tool does not invent a clean review.

`--aws-config-dir` and `--config-path` are optional so absent sources can be
reported honestly. Without a checkout, compatibility is NOT_AVAILABLE, not PASS.
Without config paths, desired-state alignment is unverified and blocks readiness.
Repository tests still run and can fail when their required config fixture is
unavailable; evaluation does not waive them. Explicit unavailable paths are errors.

Evaluation records all current WIP as provenance without treating it as an
implementation scope violation. It fingerprints the evaluated component sources
as well as the declared desired-state files and observed diff. It neither edits
nor fixes either component. `--evaluate` rejects implementation requests and
`--remediate`; even BLOCKED evaluation has zero remediation continuations.
Transitions are Architect → Verifier → Reviewer → Security → Operations →
STOP_FOR_HUMAN. Findings may keep the component BLOCKED even when every local gate
passes. A separate human-authorized implementation request is needed for fixes.

The Markdown report displays source, components, exact commands/results/log
links, readable role findings, risk table, blockers and decisions. JSON additionally
retains source/diff fingerprints and explicit mode/plan/live status. Findings are
supplied assessments, never silently inferred from a successful terraform validate.
