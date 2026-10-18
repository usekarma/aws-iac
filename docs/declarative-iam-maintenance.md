# Declarative Identity Center maintenance

This workflow supports a reviewed additive inline-policy delta on the EXISTING
IaCPlanReadOnly owner. It never generates a plan, changes a backend, adopts another
owner, or executes from an isolated planning copy. Previous workflows and receipts
are unchanged. Scope remains one inline-policy update and six unchanged managed
resources; both account assignments and baseline permissions must be preserved.
Human review of the exact delta remains essential: this is not a policy generator
or an assertion that every additive grant is least privilege.

## Contract and private evidence

Use scripts/declarative_iam_maintenance.py with --contract-file PATH. Actions are
validate (offline), seal, preflight, apply. Seal and apply are distinct human
approvals; there is deliberately no auto-seal, plan, retry or rollback command.
Do not run the real plan during workflow development or seal before workflow review.

The strict contract has these fields:

- contract: declarative-iam-maintenance-v1.
- owner_directory: existing canonical owner absolute directory (pinned by code).
- review_directory and planning_directory: absolute existing private directories.
- state_serial, state_lineage: exact reviewed authoritative baseline.
- owner_hashes: SHA256 map of ALL root .tf/.tf.json files, terraform.tfstate,
  .terraform.lock.hcl, bootstrap.tfvars.json and .terraform/terraform.tfstate.
- files: relative review file SHA256 map containing review.tfplan, plan.json,
  baseline_file, owner-context.json, rollback.json and any absent execution sources.
- baseline_file: full verified baseline declaration including both assignments.
- additions: exact approved new statement objects (unique SIDs, Allow only).
  Existing statement content/order cannot change; unexpected extra permissions fail.
- source_files: root source filenames and SHA256 values from saved-plan archive.
- evidence_files: exactly owner-context.json and rollback.json.
- reprovisioning_accounts: [623155450153, 835990279085], as strings in that order.

owner-context.json equals owner_directory/state_serial/state_lineage/owner_hashes/
planning_directory from the contract. rollback.json contains baseline (the complete
baseline declaration), automatic_rollback:false, requires_new_plan_and_human_approval:true.
Evidence must come from verified files, not invented observations. Capture source
revision, planner identity, live baseline/provisioning/assignment provenance as
additional hash-bound files. Operator-reported observations must be labeled as such.

The initialized planning copy exists only for offline terraform show -json and source/
provider-lock/state provenance verification. Its binary plan must reproduce plan.json.
No init or plan is invoked. Canonical backend must remain local/default; current
state must match the snapshot and every unchanged resource. After apply, lineage
and all seven managed resources/attributes are checked, with only policy/serial
changes permitted. Recreating a missing publisher source is allowed only from the
exact hash-verified saved-plan archive, exclusively at the original owner and only
for execution; it is removed after execution if still byte-identical. No existing
source is overwritten. Failure leaves evidence and blocks automatic retry.

## Separate approvals and execution

Approval fields (strict): operation (seal or apply), approved (true only upon actual
human authorization), contract_sha256, workflow_sha256, manifest_sha256,
reprovisioning_accounts, reprovisioning_impact_acknowledged, owner_profile,
owner_identity_arn, target_read_profile, target_read_identity_arn.
Named profiles are identity-center-admin and m1-dev-operator, respectively. Exact
operator ARNs must be verified and approved, never inferred from the profile name.
workflow_sha256 is workflow_hash(): SHA256 over concatenated SHA256 values for
all sibling Python scripts sorted by filename; this binds executable dependencies.
For seal manifest_sha256 is null. Apply binds the resulting actual manifest hash.
No human identity, signature, timestamp or approval may be fabricated.

After code review: prepare verified contract/evidence and disabled seal approval,
obtain separate seal authorization, then human terminal only:

```bash
AGENT_MODE=0 HUMAN_M1_APPLY_APPROVED=1 python3 scripts/declarative_iam_maintenance.py seal --contract-file <PRIVATE-CONTRACT> --approval-file <SEAL-APPROVAL>
```

The reused environment guard uses HUMAN_M1_APPLY_APPROVED for the seal action too;
it never substitutes for the operation-specific approval file and never applies.
Seal creates declarative-iam-manifest.json exclusively. Record/review its hash.
Obtain a NEW apply approval acknowledging automatic provisioning of BOTH accounts.
Use action preflight (AGENT_MODE=0) for fresh read-only checks, then action apply
with the same human-only environment and separate apply approval. Never use
administrator profiles in an agent session. No actual execution approval is supplied
by this documentation.

Live checks require exact STS identities, central policy, latest provisioning in
both accounts, exact USER assignments, generated-role identities, inline policies,
no boundaries or managed attachments. All successful raw replies are saved privately
before and after execution. A denied API stops; never infer absence or escalate.
AWS SDK retries are disabled where supported; no orchestration retry/rollback.

Exclusive declarative-iam-attempt.json is created and fsynced BEFORE any execution
source staging or Terraform invocation; it blocks another attempt even after failure.
Evidence directories are unique, logs/receipts exclusive. Postflight failure remains
an incomplete attempt, not successful execution; reconcile manually without rerunning
apply. Current owner and all artifacts must remain preserved. Sealing or applying
this new delta needs separate human authorization and reviewed evidence.

## Canonical state-read plan

Existing reviewed binary SHA256:
c886f05a421c02dd1f12206566d0710d05a1c1933c5b61feaf1525fb347c3fa3.
Baseline serial20, lineage adda9261-8df8-2be4-51cf-f829529878b3, 19 statements.
Only M1CanonicalOperationalStateRead may be added, as declared in merged
examples/identity-center-owner.iac-plan-readonly.m1-state-read.json. Exact resource
is arn:aws:s3:::623155450153-tf-state/iot-digital-twin/operational-demo/terraform.tfstate;
PrincipalAccount and ResourceAccount remain 623155450153. No version/history/writes.
No real contract approval or seal is created in this PR. No AWS cost from offline
validation; subsequent approved operations have existing API request charges only.
Rollback needs a new reverse plan and approval, with both-account provisioning.
