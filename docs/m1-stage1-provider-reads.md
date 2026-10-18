# M1 Stage 1 provider-read proposal

Goal: permit canonical bootstrap ownership checks and future Terraform refresh of
one Cloud Control role. No IAM application, operational deployment or SSM
publication is authorized. Use existing Identity Center Terraform owner in
835990279085, local backend/default workspace; last operator-reported serial 17.
Reverify current serial, lineage, owner source and baseline before planning.
Do not create another owner or edit the generated role directly.

Candidate: examples/identity-center-owner.iac-plan-readonly.m1-provider-read.json.
It preserves every field, all 18 baseline statements and both USER assignments,
then adds exactly one statement with four read-only actions on:
`arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control`.
The aws:PrincipalAccount condition excludes the management-account assignment.
IAM is global; do not add a regional resource ARN or an unverified regional fence.

## Six denied APIs and smallest grant

All six exact-name calls returned AccessDenied using strall-dev-plan. These are
permission findings, not role absence. Human separately reported NoSuchEntity.

| Action | Proposal | Reason in pinned AWS provider 6.69.1 |
| --- | --- | --- |
| iam:GetRole | Add | Role read, trust/boundary/tags and ownership |
| iam:ListRolePolicies | Add | Role refresh enumerates inline policies |
| iam:GetRolePolicy | Add | Role refresh reads each inline policy; separate policy resource also reads it |
| iam:ListAttachedRolePolicies | Add | Role refresh always reads attachment names |
| iam:ListRoleTags | Omit | Role refresh receives tags from GetRole |
| iam:ListInstanceProfilesForRole | Omit | Not used in ordinary role/policy refresh; teardown is outside scope |

All six support role resource scope; no Resource * is needed for this addition.
GetRolePolicy scopes to the role, not an inline-policy ARN/name. It therefore
reveals any inline policy on this exact role. Attachment listing reveals ARNs,
not managed policy contents. No iam:GetPolicy/GetPolicyVersion, ListRoles,
PassRole, AssumeRole or mutations are added. Existing broader discovery permissions
are unchanged, not newly minimized or extended by this proposal.

Source evidence (check again if provider version changes):
https://github.com/hashicorp/terraform-provider-aws/blob/v6.69.1/internal/service/iam/role.go
(resourceRoleRead, resourceRoleFlatten, readRoleInlinePolicies), and
https://github.com/hashicorp/terraform-provider-aws/blob/v6.69.1/internal/service/iam/role_policy.go
(resourceRolePolicyRead). Source inspection is not a live refresh test.

## Plan and approval criteria

Use the existing owner maintenance preparation process with this declaration as
a new candidate, after verified owner identity and refreshed baseline evidence.
Do not reuse old sealed M1 discovery plan, manifest, approvals or exact-seven-addition
sealer: they bind the previous change and must remain untouched. A later sealed/apply
path must explicitly support and review this new delta; this PR does not extend it.

Require exactly one aws_ssoadmin_permission_set_inline_policy update and six
unchanged owner resources, no replacements/imports/deletes/drift/unrelated changes.
Before policy equals all 18 current statements; after equals baseline plus the exact
four-action statement. Permission set, duration, tags and assignments unchanged.
Save binary/JSON privately, record hashes and source/context/owner integrity.
Stop on baseline or ownership mismatch. No saved plan was produced by this proposal.

Terraform updates automatically reprovision BOTH assigned accounts 623155450153
and 835990279085. New access is usable only in target account, but both provisioning
operations and propagation/error risks require separate explicit human approval.
Rollback is another reviewed owner plan removing only this addition, with both-account
reprovisioning acknowledgment; no automatic rollback or direct role editing.

## Read-only postflight after separately approved application

Verify owner central policy equals candidate, provisioning status latest in both
accounts, unchanged assignments and generated-role baseline plus this delta; boundary
and managed attachments must match preflight. Use named authorized identities only.
Refresh the reader session through the human SSO procedure and confirm STS account.
Then run GetRole on the exact proposed name: NoSuchEntity is expected before creation;
AccessDenied is a failure. Once it exists, verify trust/role ARN/tags and exercise
ListRolePolicies, GetRolePolicy (m1-flat-resource-handlers), ListAttachedRolePolicies.
Do not grant the two omitted APIs merely because their standalone probes still fail.
No create/attach/PassRole/MQTT operations are part of this postflight.

## Alternative and other blockers

For a genuinely empty first-deployment state, absent role and bootstrap module with
no role lookup, Terraform may generate a create plan without any role resource reads.
Operator-provided exact-name absence inventory can satisfy collision review, without
this grant, if current state/workspace/backend and saved-plan inspection establish that
case. Do not use -refresh=false or conceal existing-state reads. Inventory cannot
replace actual SDK permissions for existing-resource refresh or stage-2 data lookup.

The approved non-secret bootstrap config remains review-only at
artifacts/m1-operator-readiness/stage1-ssm-publication-20261018T010330Z in iot-digital-twin;
SHA256 5026becea5d503df25ac49459d8fdeb071b761268a6f08e1c30fc0f9a15aedda is unchanged.
SSM publication requires separate approval. New role ARN stays null and handler-tag
verification false. Current discovery policy has GetObject only for artifact component
state, not operational-demo state: independently verify canonical backend object read
permission before planning; do not silently add state-content access in this grant.
ATOM resources and inactive/unattached M1 certificate remain untouched.
