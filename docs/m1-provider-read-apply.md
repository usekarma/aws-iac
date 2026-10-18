# Human-only provider-read maintenance execution

This separate adapter accepts only m1-provider-read-seal-only-v1, the existing
f10b2dbdd9229073780b83f66a5b00b5e3f41f9b33dfcd5530bdf7a891e91cb4 plan and
77a35ca33f95b53e658c33a791cf50fa00ee4d92f60053f45de2eb2ae12abfc6 manifest.
Older workflows, sealed inputs and approvals remain unchanged. Matching sealing
checks are reused; execution orchestration is separate so older hash-bound source
files are not edited. Development uses synthetic fixtures only, no real apply.

## Approval schema and non-mutating preflight

scripts/apply_m1_provider_reads.py requires an exact approval object with these
fields: operation=m1-provider-read-exact-apply, approved (boolean), plan_sha256,
manifest_sha256, workflow_sha256 (SHA256 of reviewed merged adapter),
reprovisioning_accounts=["623155450153","835990279085"],
reprovisioning_impact_acknowledged (boolean), owner_profile=identity-center-admin,
owner_identity_arn (exact human management AdministratorAccess STS ARN),
target_read_profile (explicit human-controlled named reader),
target_read_identity_arn (exact account623155450153 STS ARN).
No extra schema_version/status fields are accepted. Previously prepared candidate
is a review draft, not this executable schema; do not fabricate identity/approval.

Human terminals only, AGENT_MODE=0. Preflight allows approved=false and pending
acknowledgment; it performs only reads and creates no attempt marker. It does not
infer release authorization. All identity ARNs and workflow hash must already be
verified, even for pending preflight. No administrator credentials in agent sessions.
The selected profiles never switch automatically. Credential/endpoint/argument
and alternate config-file overrides are rejected.

```bash
# Human terminal; approved=false candidate, current verified identities required.
AGENT_MODE=0 python3 scripts/apply_m1_provider_reads.py preflight \
  --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 \
  --review-dir /home/ted/dev/iot-digital-twin/artifacts/m1-operator-readiness/m1-provider-read-plan-m9ieoiw4 \
  --approval-file /PRIVATE/provider-read-approval.json
```

Preflight revalidates sealed owner state serial17/lineage/local backend/default
workspace, archive/rollback/source integrity, exact18-statement baseline plus four
reads and one-update/six-no-op contract. Fresh owner and target STS, central inline
policy, latest provisioning in both accounts, both generated role ARNs/policy names,
no boundary/managed attachments, and both USER assignments must match baseline.
AccessDenied, stale state, missing evidence or drift stops with no fallback.

## Separately approved one attempt

Only after new human APPLY approval for these hashes/workflow/identities, explicitly
covering both-account reprovisioning, set approved=true and acknowledgment=true.
Human execution uses the same command with action apply and explicit
HUMAN_M1_APPLY_APPROVED=1. That flag alone does not authorize anything; the approval
object and live checks are still required. No execution is authorized by this PR.

Adapter exclusively creates m1-provider-read-apply-receipt.json BEFORE mutation;
any existing attempt prevents a second invocation, including failed/timeout cases.
Only terraform apply of the exact saved binary is invoked; no regeneration, refresh,
import, init, config overlay or policy API writes. Plan carries its reviewed source
and historical publisher overlay. Existing owner config/state inputs are validated;
no overlay is written into the owner during execution.

One bounded process (1800 seconds), no orchestration retries or automatic rollback.
AWS CLI attempts are bounded to one; Terraform/provider internal propagation handling
is not replaced by a retry loop in this adapter. Private log and receipt record
exit code, postflight or failure type. Timeout/partial failure is uncertain outcome:
stop for operator reconciliation; do not delete attempt marker or rerun apply.

Postflight verifies retained lineage and advanced serial with exact reviewed after
attributes, all other sealed owner inputs unchanged, exact19-statement central and
both generated policies, latest provisioning and unchanged assignments, boundaries
and attachments in BOTH accounts. Management account receives same policy document,
but new grant's PrincipalAccount condition permits access only in target account.
If postflight fails after Terraform succeeds, receipt preserves exit0 and failure;
no rollback/retry. Explicit action postflight permits read-only follow-up after a
matching recorded exit0 attempt, with exclusive separate postflight receipt.

## Acceptance and residual boundaries

Tests use mocks only; live execution is not verified in development. Regressions
cover approvals/hashes, agent and override rejection, incorrect identity, live drift,
false-approval preflight, one-attempt/no-retry behavior, failures/timeouts, state
mutation and two-account policy/provisioning checks. Current cloud authorization
and freshly collected operator evidence are prerequisites, not inferred from tests.
No SiteWise, SSM publication, MQTT, certificates or ATOM operations are implemented.

Rollback, if later needed, is a new reviewed owner removal-only plan with separate
both-account reprovisioning approval. Preserve attempts/evidence and prior receipts;
never automatically rollback, reuse earlier approval or edit generated roles directly.
