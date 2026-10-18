# M1 canonical operational state read proposal

The planning role currently cannot read the canonical operational-demo state.
The additive owner declaration is
examples/identity-center-owner.iac-plan-readonly.m1-state-read.json.
It preserves all 19 statements in the merged provider-read declaration and both
assignments, adding only s3:GetObject on the exact current state object in account
623155450153. PrincipalAccount and ResourceAccount conditions preserve account
scope. No object versions, history, additional prefixes, writes, locks, PassRole,
credential reads or IAM changes are granted by the addition. Existing bucket and
DynamoDB reads are preserved. State may contain sensitive resource attributes;
retain all reads privately and never commit state.

Use the EXISTING Identity Center Terraform owner in management account
835990279085. This declaration is a candidate, not a new owner or an instruction
to edit a generated role. Independently reconcile the live current owner, serial,
lineage, 19-statement baseline and both assignments before any plan. Stop if the
baseline differs. No prior sealed plan, approval or adapter authorizes this delta.
Prepare a fresh non-mutating plan requiring one inline-policy update, six unchanged
resources, no replacements and no assignment changes. Review source and evidence,
then obtain separate apply approval. Applying would automatically reprovision both
623155450153 and 835990279085; the new statement permits access only in the former.
No plan or apply is performed by this proposal.

After separately approved application and provisioning, use strall-dev-plan STS,
then private S3 GetObject on exactly the canonical key. Verify current state serial,
lineage and ownership without restoring or modifying state. AccessDenied remains
unknown, never absent. No new recurring service cost; normal S3 request costs apply.
Rollback requires a new reviewed owner plan removing only this statement, separate
approval and two-account provisioning. Do not reuse old saved plans.
