# Declarative IaCPlanReadOnly and explicit human bootstrap

Status: STOP_FOR_HUMAN — locally prepared; human must generate/review live plan.
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
No bootstrap apply command is implemented. Eventual mutation needs a separate
reviewed human path, current saved-plan review and AWS_MUTATION_APPROVED=1 after
explicit approval; the bootstrap acknowledgement alone is insufficient.

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

No objects/data are changed by this task. Future rollback/revocation is a new
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
resource list and values privately, record the digest and stop. No apply command
is provided by this change. Bootstrap acknowledgement does not authorize a saved
plan execution. Human approval of any future concrete apply is still required.

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
No live human bootstrap invocation, AWS calls, config publication, apply or
profile edits occurred. Agent mode remained enabled for this task; test fixtures
mock human environments/tools without authorizing real bootstrap operations.
