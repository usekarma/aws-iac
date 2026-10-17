# M1 exact sealed-plan human apply/postflight

This M1-only extension leaves older maintenance and sealing contracts unchanged.
Development runs mocks only. It neither replans nor regenerates or reseals artifacts.
Approved binary: 6b4420f0fd9c9c1c5f44fe4dae0264c1fd21935591d469b3f9a16804856ef34d.
Approved manifest: 666c5e8f55bc840e1c937d8d1b499ed9f0dee270f5574e88d7266c4e0753be16.

## Diagnosis and execution boundary

Read-only terraform show failed inside the agent sandbox loading the AWS 6.68.0
plugin schema: the plugin handshake emitted no initial protocol output. ELF
architecture/executable mode matched the host. The SAME command against the SAME
binary succeeded outside sandbox restrictions and its JSON matched saved plan.json.
This establishes an execution-environment restriction; it does not identify the
specific kernel restriction. No provider, source, credentials, plan or state repair
is needed. Run from the operator's working terminal; do not skip binary rendering
or substitute unverified JSON when it fails. Schema rendering is read-only and
needs local provider execution, not an infrastructure apply.

## Before any human execution

Review/merge the workflow and independently bind its source hash in a NEW private
approval file. Existing seal_only approval is not apply approval. The apply file
must contain exactly these fields (replace identity/profile/hash values with actual
independently reviewed values, not placeholders):

```json
{
  "operation": "m1-discovery-exact-apply",
  "approved": true,
  "plan_sha256": "6b4420f0fd9c9c1c5f44fe4dae0264c1fd21935591d469b3f9a16804856ef34d",
  "manifest_sha256": "666c5e8f55bc840e1c937d8d1b499ed9f0dee270f5574e88d7266c4e0753be16",
  "reprovisioning_accounts": ["623155450153", "835990279085"],
  "owner_profile": "identity-center-admin",
  "owner_identity_arn": "REPLACE_WITH_APPROVED_EXISTING_OWNER_OPERATOR_STS_ARN",
  "target_read_profile": "REPLACE_WITH_EXISTING_AUTHORIZED_TARGET_READER",
  "target_read_identity_arn": "REPLACE_WITH_APPROVED_TARGET_READER_STS_ARN",
  "workflow_sha256": "REPLACE_WITH_REVIEWED_APPLY_SCRIPT_SHA256"
}
```

Owner identity must be the existing Identity Center administration profile in
835990279085, not the target reader. No AssumeRole or new credentials are created.
The target read identity must already be authorized for generated-role policy
inspection in 623155450153. Both profiles are approved explicitly; there is no
automatic administrative fallback. Operator must have the established owner SSO
write/provision privileges; failures never expand them. Approval records are local
attestations, not signatures; protect files and hashes independently. No mutation
is authorized by this documentation or by tests passing.

## Human-only invocation after workflow/operation approval

Use the existing owner and review paths; no concurrent maintenance. The local
backend's actual Terraform lock is enabled for apply; no force-unlock, -target,
-auto-approve, override variables, overlay insertion, backend init or state copy.
The saved plan contains its reviewed publisher sources, so apply does not insert
an overlay or change declarations in the original owner directory.

```bash
# Human terminal only; agents must never run this during development.
export AGENT_MODE=0 HUMAN_M1_APPLY_APPROVED=1
python3 scripts/apply_m1_discovery.py apply --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/m1-discovery-1dhfxzlv --approval-file /PRIVATE/m1-apply-approval.json
```

Before mutation the workflow verifies exact owner STS identity, all seal hashes,
source/state/backend/workspace/provenance and actual binary contents through the
existing sealer, and live baseline permission set/generated roles/assignments in
both accounts. Exactly one policy update and six no-ops must pass again. Unexpected
live boundary or attachments, policy drift, missing reads or identity mismatch stop.

The exclusive m1-apply-receipt.json is created BEFORE the single apply attempt.
Existing receipt prevents repeating apply. Terraform saved-plan stale-state checks
also remain enabled. There is no automatic retry or rollback; CLI API reads have
AWS_MAX_ATTEMPTS=1. Internal provider behavior for the archived approved provider
is unchanged; the workflow never repeats the Terraform apply process. A timeout or
partial apply may leave partial AWS/state effects: retain the log, stop and request
operator investigation. No assumption that failure means no changes.

## Postflight and receipts

On successful Terraform exit, verify local lineage/serial and exact reviewed
managed after-state, sealed evidence/provider/source integrity, exact permission-set
inline policy, both accounts latest-provisioned, and actual generated-role inline
policies with no managed policies/boundaries. Assignments must match the declaration.
The same added JSON is present in both roles, but PrincipalAccount guards make new
grants ineffective in 835990279085. This verifies policy delivery, not universal
runtime authorization: SCP absence is still operator-attested; resource/endpoint
policies may affect real reads. There is no MQTT or device operation in verification.

Terraform automatically reprovisions BOTH assigned accounts. Preserve publisher
and all assignments; ATOM resources, producer credentials and SiteWise are outside
this workflow and never called. Local state is permitted to change ONLY during
separately authorized apply, not during development or validation.

Success/failure is recorded in m1-apply-receipt.json; m1-apply.log stays private.
A failed postflight after exit 0 records that apply completed and stops. An explicitly
requested subsequent read-only postflight may use the postflight subcommand with
the SAME approval; it requires a successful recorded exit and creates an exclusive
m1-postflight-receipt.json. It never repeats apply or reprovisions. Neither receipt
modifies the immutable seal's original evidence inventory. Do not retry automatically.

Rollback remains a NEW separately reviewed same-owner reverse plan, not this
script or old state restoration. Residual risks: network/access failures, concurrent
external drift between checks and execution, SSO/session expiry, partial provisioning,
and operator-attested SCP controls. No live apply or postflight result is claimed
by this PR. Behavioral tests mock all mutations and cannot prove service execution.

Acceptance: M1-APPLY-01 exact hashes/human identity/source binding; M1-APPLY-02
single saved-plan attempt; M1-APPLY-03 after-state and two-account verification;
M1-APPLY-04 fail-closed receipts/no retry/rollback; M1-APPLY-05 no device/producer/
SiteWise operations. Prior contracts remain unchanged.
