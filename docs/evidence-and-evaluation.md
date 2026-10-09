# Review evidence and evaluation

## Safe workflow

1. Write a short spec with objective, exact target, preservation constraints and
acceptance checks. Inspect both repos and their revisions; do not treat config as approval.
2. Export AGENT_MODE=1. Run make verify and make test. Config: additionally run
AWS_IAC_DIR=../aws-iac make verify and python3 scripts/validate_config.py.
3. With independently confirmed AWS_PROFILE, AWS_REGION, EXPECTED_AWS_ACCOUNT,
EXPECTED_ENVIRONMENT, EXPECTED_BINDING and IAC_PREFIX, run scripts/preflight.sh.
Use a read-only IAM role. In aws-iac, run scripts/plan.sh COMPONENT NICKNAME
(or add --destroy to prepare a teardown proposal). No backend bootstrap is allowed.
4. In the exact resulting component cache directory, privately export the saved plan:
terraform show -json review.tfplan > /PRIVATE/PATH/plan.json
Use umask 077 first. Plan/state values may contain credentials. Do not publish raw output.
5. Copy examples/review-context.synthetic.json into a private context file. Replace
all synthetic targets/context, set synthetic=false, record both repo commits, changed
files, validation outcomes, recovery and postflight checks. Never put secret values
in context. From repo root run:

```bash
python3 scripts/evidence.py --plan-json /PRIVATE/PATH/plan.json \
  --saved-plan /EXACT/CACHE/review.tfplan --context /PRIVATE/PATH/context.json \
  --output artifacts/review-UNIQUE
```

The generator writes JSON and Markdown with resource identities/actions, delete and
replacement risks, persistent resources, IAM/network flags, drift count, unknown
values and plan digests. It copies no before/after/output values. Treat even this
summary as private: context and resource addresses can still be sensitive. The binary
plan digest identifies the file but does not prove the JSON was exported from it;
the reviewer must check provenance. Context is supplied, not attested. Missing plan
completeness metadata is reported as unverified; errored/incomplete plans fail.
6. Review blast radius, regional aliases, expected data loss, backups/restore evidence,
surviving data and cost leftovers. Strong destructive approval is needed for deletes,
replacements or state-forget. Every AWS execution/publication still needs human approval.
7. Stop. A separately authorized human path executes the exact approved saved plan
or publishes the exact config. An inherited acknowledgement never overrides agent mode.
Regenerate/review after any code/config/state/identity change. Native default apply
can generate a new plan, so the human must compare it at confirmation.
8. Run read-only postflight and inventory; observe service health and cost. Do not
use postflight success as permission for further deletions.

## Postflight expectations

Prepare a PRIVATE JSON list with exact reviewed IDs/SSM paths:

```json
[
  {"type":"volume","id":"vol-0123456789abcdef0","expected":"absent"},
  {"type":"snapshot","id":"snap-0123456789abcdef0","expected":"present"},
  {"type":"ssm","id":"/iac/vpc/usekarma-dev/runtime","expected":"present","required_keys":["vpc_id","private_subnet_ids"]},
  {"type":"ssm","id":"/iac/vpc/usekarma-dev/config","expected":"present","expected_json_file":"/PRIVATE/APPROVED/config.json"}
]
```

python3 scripts/postflight.py --expectations /PRIVATE/PATH/expectations.json runs
preflight, then only allowlisted describe/get commands. Failures/denied permissions
are failures, not evidence of absence. EC2 terminated instances count as removed.
SSM comparison prints booleans only; no parameter values. `scripts/inventory.sh --output artifacts/inventory-UNIQUE` writes private JSON and
a cost-review report. Account-wide inventory
in aws-iac surfaces detached EBS, unassociated EIPs, self-owned snapshots/AMIs,
NAT and ALB. Those are review candidates, never automatically safe to delete.
Health endpoints, ECS/DNS/S3 restore tests and all other affected services must be
verified in the spec; this small script does not claim full application health.

## Reproducible offline demonstration

make demo uses an explicitly synthetic plan of deleting a ClickHouse EBS volume and
instance while preserving a separately managed backup bucket. It generates private
evidence under artifacts/. It never contacts AWS or executes Terraform. Investigation:
read architecture-assessment.md, ClickHouse main.tf/mongo.tf/redpanda.tf, and prod
config; proposed change is a teardown *proposal*, not authorization. Validation:
make verify. Planning stage uses a fixture, not a current AWS plan. Expected report:
strong destructive approval, data-loss/root-volume warnings and survival/cost caveats.
Prepare the verification expectations and stop at the approval boundary. The next real
experiment is a read-only, non-production plan with independently verified targets.

## Lightweight evaluation

Keep a private per-task JSON/CSV record: task ID, objective, start/end UTC, agent/repo
versions, offline results, plan digest, human corrections, approval outcome, blocked
unsafe attempts, postflight outcome and incidents. Do not include credentials/values.
Measure over a small weekly sample:

| Metric | Measurement |
| --- | --- |
| Autonomous preparation | Tasks reaching validated proposal without manual command fixes / tasks |
| Defects caught before AWS | Failed schema/lint/test/static gates with a confirmed defect |
| Plan acceptance | Plans accepted unchanged / plans reviewed |
| Human correction rate | Agent proposals requiring correction / proposals |
| Unsafe actions blocked | Verified blocked mutation attempts; synthetic and real tracked separately |
| Objective-to-plan time | Minutes to validated, reviewable live plan; fixture time separate |
| Agent-related incidents | Confirmed production failures attributable to accepted agent changes |
| Postflight success | Complete expected checks passed / executed approved changes |

Pilot five small tasks. Keep production readiness unclaimed until live planning,
restore and verification evidence exists. Compare with the previous manual workflow;
revise contracts from observed failures rather than adding a telemetry service.
