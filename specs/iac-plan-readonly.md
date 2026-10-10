# Declarative IaCPlanReadOnly and explicit human bootstrap

Status: observed — human bootstrap/apply/postflight completed; ready for merge review.
Owner/reviewer: strall / requesting human. Branch: feature/iac-plan-readonly.
No live planning, apply or AWS mutation is authorized for the agent in this task.

## Goal and trust boundary

Solve the initial planning-role bootstrap dependency without weakening ordinary
agent planning. The explicit human-only planner uses the same generic Terraform
resources and checked-in declaration with a private local backend. It does not
require or create owner SSM binding/config prerequisites. The normal runner,
preflight, Terragrunt and AGENTS.md remain unchanged by this bootstrap update.

AdministratorAccess is acceptable only for the one-time HUMAN bootstrap of
IaCPlanReadOnly. Agents never use this bootstrap path. After IaCPlanReadOnly
exists, normal agent workload planning uses the restricted role.
HUMAN_BOOTSTRAP_APPROVED=1 authorizes human entry only, never apply.
AGENT_MODE=1 always rejects bootstrap, even with inherited mutation approval.
The explicit saved-plan apply path requires BOTH acknowledgements, a reviewed
external manifest digest and all integrity/live identity checks. The bootstrap
acknowledgement alone is insufficient. Implementing this path is not permission
for an agent to execute it.

## Exact reviewed target

- Owner administration account: 835990279085; region: us-east-1.
- Human profile: identity-center-admin; STS must identify owner AdministratorAccess.
- Instance: arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91.
- Existing IdentityStoreId: d-9067ccec40 (not managed).
- Permission set: IaCPlanReadOnly; session duration: PT1H.
- Assignment: target 623155450153, USER b4486448-d011-7037-9cfb-c16c43f591e1,
  username admin, display name Admin.
- Fixed local declaration: examples/identity-center-owner.iac-plan-readonly.json.
- Canonical reviewed inline-policy SHA-256:
  43f0d7d3f42e95037872b8e90ec11228f2ab869382fdc13c27b493b3e5423d0e.

Read-only discovery in the previous task confirmed the owner account and the
existing AdministratorAccess permission set. IaCPlanReadOnly was absent. The
human bootstrap planner repeats these checks immediately before each plan;
prior evidence is not permission to skip discovery. Any access denial stops.

## Exactly expected bootstrap plan

Three creates, zero changes/deletes:

1. aws_ssoadmin_permission_set.permission_set
2. aws_ssoadmin_permission_set_inline_policy.inline_policy
3. aws_ssoadmin_account_assignment.assignment["623155450153/USER/b4486448-d011-7037-9cfb-c16c43f591e1"]

Runtime SSM was unnecessary for this component and is removed. No SSM parameter,
managed-policy attachment, instance, store, user/group, Organizations, S3/backend
or direct IAM-role resource is managed. Native Identity Center provisioning of
an AWSReservedSSO role would occur only after separately approved execution.
Reject any unexpected resource, update/delete/replacement/drift, incorrect
instance/name/duration/assignment or policy difference. Existing IaCPlanReadOnly
always stops bootstrap rather than proposing duplication or adoption.

## Preservation, state and recovery

Preserve every existing permission set, assignment, instance/store/principal,
workload resource, bucket, backend and SSM parameter. The inline policy is the
exact human-supplied seven-statement, 24-action read-only document; no managed
admin/read-only policy attachments, kms:Decrypt or mutation actions are added.
Tags follow Project/Component conventions with owner/purpose/owner-context tags.

Raw plan, JSON, logs, declaration variables and digests remain private under
ignored artifacts/identity-center-bootstrap/review-* with restrictive permissions.
The snapshot-only local backend needs no AWS storage bootstrap. Do not run the
normal remote-state component against the same resources after bootstrap: state
ownership remains with the bootstrap snapshot until a separately reviewed
migration. Never discard eventual applied state or repair/migrate it casually.

This documentation finalization changes no infrastructure. The human bootstrap
created the reviewed permission set/policy/assignment. Future rollback/revocation is a new
reviewed operation; permission-set deletion can revoke user access. CloudTrail
would audit future admin actions. No new logging/alarm/backup resources are
required for plan preparation. Propagation/availability/role access and attached
policy lists require read-only postflight after separately approved execution.

## Human command and review

From the repository root, personally run:

```bash
AGENT_MODE=0 HUMAN_BOOTSTRAP_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/bootstrap_identity_center.py plan identity-center-permission-set
```

The planner writes the exact saved review.tfplan, private terraform.log and
plan.json, filtered discovery/context and evidence JSON/Markdown. Review both the
resource list and values privately, seal exact inputs and record the manifest
digest externally. Bootstrap acknowledgement does not authorize saved-plan
execution. Separate human approval of the concrete apply is still required.

After separately approved provisioning/assignment, configure strall-dev-plan and
verify account/role/read-only grants. Then ordinary agent workload planning uses
normal preflight/config/SSM; the planning role cannot administer its own bootstrap.
See the component README for the profile stanza and state-ownership guidance.

## Verification

Run make verify, make test, changed Python Ruff format/lint, recursive Terraform
fmt -check, git diff --check, and scripts/verify.sh --terraform
identity-center-permission-set. Deterministic tests cover acknowledgement/agent
rejection, wrong expected/actual account, forbidden overrides/actions/components,
existing permission-set detection, no SSM discovery or runtime resource, local
backend/evidence, exact policy/USER/target, plan action/resource rejection and
separate normal mutation approval. Normal preflight and other component tests
continue unchanged. Mock Terraform tests cover normal SSM and bootstrap inputs.
No live bootstrap plan or evidence is represented by local test fixtures.

## Local validation results (2026-10-09)

make verify and make test pass with AWS_CONFIG_DIR=../aws-config: 76 Python
tests, one existing skip. Four Terraform mock-provider plan tests pass.
scripts/verify.sh --terraform identity-center-permission-set passes backend-disabled
init/validate. A disposable copy also verified that bootstrap_override.tf selects
only the local backend. Recursive Terraform fmt, git diff --check and changed
Python Ruff format/lint pass. Terraform 1.15.2, Terragrunt 0.83.2, AWS provider
6.68.0. Initial formatting/generated-HCL errors were corrected and checks rerun.
These implementation-time tests used mocked human environments/tools. The agent
kept agent mode enabled and did not execute bootstrap; the subsequent successful
human execution is recorded below.

## Human-only saved-plan apply extension

The requesting human identified review-uhd86fs8 as reviewed: three creates, no
changes/deletes. Its original binary/JSON evidence digests and checked-in component
snapshots match; no source/resource or declaration changes are needed for apply.
The bundle originally predated manifests and has now been sealed by the human.
The explicit human `seal` action verifies archived
configuration/provider lock, original evidence/context, repository identity/commit
ancestry, checked-in configuration, local backend and binary export/JSON equality.
It creates an exclusive read-only manifest without changing the plan or evidence.
Its SHA-256 must be reviewed and held independently; apply rejects a different
manifest even if someone recomputes all internal file hashes. Permission bits and
self-reported context are not independently authenticated approval evidence.

Apply accepts only a real review-* directory under this repository's bootstrap
artifact root, never an arbitrary tfplan. Both human flags and AGENT_MODE=0 are
required before any tools are invoked. It hashes every material bundle input plus
current scripts/declaration, validates repository/commit ancestry and component
identity, re-exports the saved binary and verifies exact three-create resource
TYPES/addresses, instance/name/duration, policy and USER/account. New local state,
workspace/backend/variable overrides, changes/deletes/replacements/managed-policy
attachments or existing IaCPlanReadOnly all stop execution. STS and Identity Center
discovery repeat immediately before apply. No replan/init is allowed during apply.

The only mutation entrypoint is Terraform apply of the exact saved review.tfplan.
After success, read-only verification checks existence/PT1H, exact inline policy,
empty AWS/customer-managed policy lists and the reviewed USER assignment. Private
apply.log and post-apply.json record results. Failure may follow partial mutation;
never retry/apply/destroy automatically, configure profiles or perform SSO login.
Retain local state securely. No instance, Identity Store, SSM or workload mutation
is separately invoked by this control-plane path.

The component README contains the exact two-step seal/apply commands. The agent
only implements and tests this path using mocks and local read-only inspection;
no sealing of the actual bundle or AWS apply is authorized in this task.

## Apply-path local validation (2026-10-09)

make verify and make test pass with AWS_CONFIG_DIR=../aws-config: 84 Python
tests, one existing skip. Ruff format/lint, recursive Terraform formatting and
diff whitespace checks pass. Backend-disabled Terraform validation passes with
Terraform 1.15.2 / AWS provider 6.68.0. The component Terraform definitions and
reviewed declaration are unchanged by this apply extension. Local read-only
Terraform show confirmed the existing saved binary exports exactly to the
reviewed plan.json; original evidence digests still match. The agent did not seal
or apply during implementation. The human subsequently sealed/applied successfully,
as recorded below. Normal deployment safeguards and AGENTS.md remain unchanged;
apply/postflight tests continue using mocked tools and synthetic bundles only.

## Completed human execution and subsequent restricted planning

The human reported successful execution, corroborated by the retained local
manifest, bootstrap state and verified post-apply result. Execution sequence:

```text
identity-center-admin → owner account 835990279085 → sealed saved plan
  → explicit human apply approval → successful apply → read-only postflight
  → strall-dev-plan successfully used for ordinary workload planning
```

- Reviewed bootstrap plan: 3 creates, 0 changes, 0 deletes.
- Reviewed manifest SHA-256, explicitly supplied for this execution record:
  `83b7fda1f7f3f66c5311d2199a3f7426862ffd95fbd3341c5826da455ea27c3c`.
- IaCPlanReadOnly was created with the exact reviewed inline policy and PT1H.
- USER b4486448-d011-7037-9cfb-c16c43f591e1 was assigned into account 623155450153.
- Read-only postflight succeeded; no AWS/customer-managed policies were attached.
- Local bootstrap state is retained privately in the applied review directory.
  Do not rerun seal/apply or adopt these resources into a second state owner.
- Bootstrap did not configure a CLI profile. The separately authorized profile
  configuration and SSO login succeeded afterward.
- Resulting workload planning identity: account 623155450153,
  role AWSReservedSSO_IaCPlanReadOnly_92e4b2f1ca02a611, profile strall-dev-plan.
- PR #11 then used that restricted identity successfully: preflight passed and
  its artifact-bucket plan had 6 creates, 0 changes/deletes, expected resources only.
  No artifact-bucket apply or Lambda ZIP upload occurred.

Only this human-supplied manifest digest and non-secret execution summary are
recorded here; raw plans, state, logs and postflight evidence remain private and
untracked. No reviewed policy, Terraform resource or bootstrap behavior is changed
by finalizing these documents. Merge review is separate from AWS authorization.
