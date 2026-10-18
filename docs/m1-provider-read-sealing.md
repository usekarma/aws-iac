# Exact provider-read plan sealing — offline review contract

Business outcome: independently reviewable integrity seal for the existing Stage 1
reader maintenance plan, enabling a later human execution decision. This is not an
IAM application workflow. Older seal/apply scripts and approvals are unchanged.

`scripts/seal_m1_provider_reads.py` supports verify and seal only; no AWS API calls,
Terraform plan/init/refresh/apply, provisioning or automatic rollback. Offline
Terraform show uses the owner's installed locked provider, so its local plugin
execution must be permitted. A schema/render failure stops validation.

## Bound inputs and acceptance

- Exact existing saved plan f10b2dbdd9229073780b83f66a5b00b5e3f41f9b33dfcd5530bdf7a891e91cb4
  and its recorded JSON, preflight and result file digests are pinned in source.
- Existing authoritative local owner, default workspace, state serial17 and lineage
  adda9261-8df8-2be4-51cf-f829529878b3; exact owner state/source/backend/lock hashes.
- Verified serial17 receipt and prior publisher overlay are integrity checked;
  manifest retains their hashes. Their reuse is provenance, not approval reuse.
- Eighteen baseline statements remain; exact four-action statement on the exact
  M1 Cloud Control role in account623155450153 with PrincipalAccount condition.
  Declaration hashes and structural preservation checks prevent arbitrary edits.
- One planner inline-policy update and six unchanged resources, no replacement,
  assignment/publisher changes, import or drift. Binary source, provider lock,
  managed-state snapshots, supplied variables and rendered JSON must agree.
- Structured recorded preflight/result evidence is used as-is, not converted into
  invented live checks or timestamps. Recorded planner must be the named owner
  read-only role. Rollback declaration must equal the pinned full old declaration.
- Separate explicit seal-only approval binds plan/state/workflow hashes and both
  eventual reprovisioning accounts; apply_approved must be false.
- Exclusive-create read-only manifest, no overwrite/reseal. No apply is supported.

Regression IDs are the named tests in tests/test_m1_provider_sealing.py; synthetic
fixtures alone may be sealed during testing. No real bundle was sealed in development.

## Evidence preparation after workflow review

The accepted bundle path is exactly:
/home/ted/dev/iot-digital-twin/artifacts/m1-operator-readiness/m1-provider-read-plan-m9ieoiw4/
It remains at its original location; no duplicate Terraform owner or state.

Before any approved seal, verify existing hashes and current owner evidence again.
The only missing rollback input can be derived from the verified source declaration
examples/identity-center-owner.iac-plan-readonly.m1-discovery.json, whose SHA256 is
ff38cab5e8bcf9fd305d3928f54a7d142a2b64d641bb900a3941bc75fc04b62d.
Copy it exclusively as rollback-declaration.json into the private bundle, without
changing any existing evidence. A mismatch requires stopping, not rewriting a file.
This development task has not prepared or modified those real inputs.

Human prepares a private approval file only AFTER reviewing the new workflow and
this exact plan. Required JSON fields are schema_version=1,
operation=m1-provider-read-seal-only, plan_sha256 (pinned plan above), state_sha256
352ecfe3b3fcbdf1d5a75446171d449aded3ba2849cd0a550922f0c877f3027e,
workflow_sha256 (sha256sum of the reviewed merged script),
eventual_reprovisioning_accounts=[623155450153,835990279085] as JSON strings in
that order, reprovisioning_impact_acknowledged=true, seal_only_approved=true,
apply_approved=false. An unsigned pending template may have false approval fields,
but verify/seal deliberately reject it. Do not manufacture human authorization.

```bash
# AFTER separate workflow and seal-only human approval; no apply command exists.
python3 scripts/seal_m1_provider_reads.py verify \
  --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 \
  --review-dir /home/ted/dev/iot-digital-twin/artifacts/m1-operator-readiness/m1-provider-read-plan-m9ieoiw4 \
  --approval-file /PRIVATE/human-seal-only.json
# Only after successful verify and explicit seal authorization: same command with seal.
```

A manifest is written as m1-provider-read-manifest.json mode0400 and binds its
inputs, approval and implementation hashes. It never authorizes execution.
Both accounts are automatically reprovisioned by the eventual inline-policy update;
target-account condition limits new access, not provisioning blast radius.
A compatible future apply workflow, new explicit apply approval and fresh authorized
live identity/policy/assignment checks remain required. Prior discovery apply/seal
workflows must not accept this new contract implicitly. Rollback would require a new
reviewed removal-only plan and both-account provisioning approval.

No new services, costs or permissions are introduced by sealing. ATOM/certificates,
SSM, operational state and prior sealed plans/receipts are untouched. Live AWS
readiness and human release authority remain separate from offline gate success.
