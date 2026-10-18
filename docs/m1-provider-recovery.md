# Provider-read recovery binding

Objective: recover from a failed maintenance attempt whose live policy and all seven
managed attributes remain the18-statement baseline. A new saved plan requires new
approval, not retrying the failed plan. Older workflows and sealed artifacts stay
unchanged. scripts/m1_provider_recovery.py adds verify/seal/preflight/apply for a
fixed policy delta and hash-bound recovery context; it never generates a plan.

A separately reviewed private binding JSON contains exactly schema_version=1,
owner_directory, review_directory (new bundle), serial (integer >=18), lineage,
state_sha256, source_commit, review_hashes (new review.tfplan, plan.json,
preflight.json and result.json hashes), recovery_hashes, raw_directory, prior_review, prior_manifest_name (original or recovery manifest).
The same canonical local/default owner and lineage remain mandatory. This is not
an arbitrary IAM-policy interface: baseline/candidate declarations remain pinned,
all18 statements are unchanged and only the original exact four role reads are allowed.

Recovery hashes must cover all14 raw responses plus capture-hashes.json, and prior
failed receipt, plan JSON/binary and sealed manifest. Raw central/generated policies,
no boundary or managed attachments, both latest-provisioned accounts, and exact USER
assignments are revalidated. Prior failed receipt must bind old manifest/plan hashes;
current managed state must equal that plan's before-state. This prevents recovery
after a partial policy change. Access/ownership mismatch requires reconciliation,
not weakened checks or state restoration. Evidence capture time/freshness is a human
review responsibility; recorded responses do not substitute for apply live checks.

New seal-only approval has the existing provider-read seal schema, with operation
m1-provider-read-recovery-seal-only and an additional binding_sha256. Require explicit
both-account acknowledgment, seal_only_approved=true, apply_approved=false and exact
new plan/state/workflow hashes. It must come from actual new human authorization.
Exclusive-create m1-provider-read-recovery-manifest.json binds context/evidence/source
hashes. No overwrite or reuse of old manifest/approval. Verify never writes a seal.

New execution approval uses operation=m1-provider-read-recovery-apply, approved,
workflow_sha256, plan_sha256, manifest_sha256, binding_sha256,
reprovisioning_accounts, reprovisioning_impact_acknowledged, owner_profile,
owner_identity_arn, target_read_profile, target_read_identity_arn. Other fields reject.
Human-only environment guard and named verified identities are reused. Preflight
permits approved=false but still checks exact hashes and fresh live baseline/roles/
assignments/provisioning. Apply requires true approval and both-account acknowledgment.

Only saved-binary apply, exclusive durable attempt marker, one bounded invocation,
no orchestration retry or automatic rollback. Failure/timeout receipts preserved.
Postflight checks advanced same-lineage state exactly matches reviewed after-state,
all other sealed files unchanged, and exact policy/provisioning/assignments/role
boundaries and attachments in BOTH accounts. An uncertain execution stops for human
reconciliation; this extension does not erase attempt markers or restore state.

CLI: python3 scripts/m1_provider_recovery.py verify|seal|preflight|apply --owner-dir
/EXISTING/OWNER --review-dir /NEW/REVIEW --binding-file /PRIVATE/binding.json
--approval-file /PRIVATE/approval.json. Seal/apply require separate explicit human
approval; applies only in human terminal, never automated administrator sessions.
Do not use these commands on the real bundle before workflow review/approval.

Current pending candidate: plan624d44dd13f19874d00ef1fdfb2b58e3ebf3ac2a159d0ce5943e4583d5d2739d,
state serial18; reconciliation captured14 verified raw files. This PR does not prepare
human approval, seal, apply, publish SSM, or change any real plan/evidence/permissions.
Remaining production prerequisites include current operator evidence, source review,
hash-bound approvals and explicit automatic provisioning of BOTH623155450153 and
835990279085. No new cloud services or runtime costs. Rollback is a separate reviewed
plan/approval; never automatic.
