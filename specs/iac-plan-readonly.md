# Declarative IaCPlanReadOnly bootstrap

Status: STOP_FOR_HUMAN — local implementation; live administration context absent.
Owner/reviewer: strall / requesting human.
Base: current main `abc0b9291d52f9b799bc7b82adc36a18d33a2dc8`.
Independent of artifact-bucket PR #11; no S3 implementation changes included.

## Goal and measurable acceptance

Replace manual Identity Center permission-set/policy/assignment commands with a
reusable SSM-configured Terraform component and existing Terragrunt orchestration.
The exact reviewed policy, one-hour session and existing USER assignment must
survive deterministic tests unchanged. Wrong-account wrapper execution must stop
before SSM/backend access; direct Terraform provider account restriction adds
defense in depth. No live AWS operations are authorized in this task.

## Exact target and scope

- Administration account: `835990279085`; region: `us-east-1`.
- Instance: `arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91`.
- Existing IdentityStoreId: `d-9067ccec40` (not managed by this component).
- Permission set: `IaCPlanReadOnly`; session: `PT1H`.
- Target account: `623155450153`.
- Principal: USER `b4486448-d011-7037-9cfb-c16c43f591e1`, username admin,
  display name Admin; provided explicitly by the requesting human.
- Component/nickname: `identity-center-permission-set` / `owner-iac-plan-readonly`.
- Prefix: `/iac`; owner-account config/runtime SSM paths use that component/nickname.
- State key: `identity-center-permission-set/owner-iac-plan-readonly/terraform.tfstate`;
  existing owner backend names would be `835990279085-tf-state` and
  `835990279085-tf-locks`. Their existence is unverified; do not create them.
- Administration profile, environment type and exact owner binding: unknown;
  required before live preflight. None is inferred from a workload/profile name.

## Implementation and architecture

The generic component supports configuration-driven name, description, duration,
instance ARN, inline-policy object and multiple stable-key USER/GROUP assignments.
Normal SSM input/runtime and Project/Component tags remain. It adds no managed
policy attachments or manual deployment entrypoint. Existing Identity Center and
principals are externally supplied identifiers. The example declaration is not
published config; aws-config and local AWS profiles remain untouched.

The runner explicitly passes its selected component into preflight. For this
component, preflight fixes owner account 835990279085 and us-east-1, then verifies
actual STS identity against that account before reading the normal binding. Thus
current strall-dev, strall-com, dev-iac, prod-iac, karma and prod-karma identities
fail regardless of user-provided EXPECTED_AWS_ACCOUNT overrides. Profile names
remain aliases: an independently verified future owner profile can work after
actual STS/binding verification. Direct provider allowed_account_ids and resource
preconditions reject incorrect administration identities/configuration. These
checks cannot replace IAM or authorize mutation.

## Expected eventual plan

If no existing managed resources/collisions are found, expect four creates:

1. `aws_ssoadmin_permission_set.permission_set`
2. `aws_ssoadmin_permission_set_inline_policy.inline_policy`
3. `aws_ssoadmin_account_assignment.assignment["623155450153/USER/b4486448-d011-7037-9cfb-c16c43f591e1"]`
4. `aws_ssm_parameter.runtime` in the owner account at
   `/iac/identity-center-permission-set/owner-iac-plan-readonly/runtime`.

Runtime publication is the standard supporting component resource, not a grant in
the planning role's inline policy. No instance/store/principal creation, IAM role
resource, managed-policy attachment, Organizations change, S3 bucket or data
resource is declared. Preserve existing assignments, permission sets, instance,
store, owner backend, artifact/state buckets and all persistent data. Stop on
updates, replacements, deletes or unexpected resources pending renewed review.

## Security and operational considerations

The inline policy is exactly the supplied seven-statement JSON: 24 distinct read
actions and narrowly identified resources, with resource '*' only where specified.
No managed AdministratorAccess/PowerUserAccess/ReadOnlyAccess attachments,
kms:Decrypt or mutation actions are added. All ungranted actions are implicitly
denied; do not later attach broader policies without separate review. Identity
Center's native provisioning may produce the AWSReservedSSO role after approved
assignment; Terraform does not directly manage that IAM role.

Use owner-context read-only IAM for live planning. The elevated human owner
identity is only for separately approved administration execution. The resulting
workload planning role cannot administer its own permission set and is not a
general account-wide planning role. Keep AGENT_MODE=1 and all existing approval
guards. No need to weaken AGENTS.md or combine production workload changes.

Use CloudTrail for future administrative audit; this task adds no logging/alarms
infrastructure. Permission-set availability and assignment propagation require
postflight observation. Session duration is one hour. No stored credentials or
userdata are involved. No data-storage deletion or backup change is proposed.
Cost/health/restore evidence is pending eventual execution, not inferred from tests.

## Verification

Run make verify, make test, Ruff format/lint on changed Python, recursive Terraform
fmt -check, git diff --check, and scripts/verify.sh --terraform
identity-center-permission-set. Mock-provider Terraform plan tests verify the
reviewed declaration and reject wrong caller/configured owner. Python tests pin
the exact canonical policy digest, expected read-action set, principal/target/name/
duration and resource types; shell tests reject all six wrong-profile accounts,
incorrect expected account/region, and preserve backend/agent plan guards.

No live plan, saved-plan digest or actual evidence is generated. Once a verified
owner read-only profile, actual binding/config/schema and existing backend are
supplied, use scripts/plan.sh and inspect the private saved plan. Run evidence.py
on genuine private plan JSON/context, with no secret/plan values committed.

## Failure, recovery and approval

Stop on unauthorized account, access denial, missing binding/backend, name or
assignment collision, or drift. Do not add broad permissions to bypass denied
reads. Adoption/import/state repair requires its own explicit scope and review.
For later failure, inspect provisioning/assignment status without deleting or
revoking unrelated access. Rollback uses a new reviewed Terraform/config plan;
permission-set deletion can revoke user access and always needs human approval.

Human approval remains required for aws-config publication, any backend creation,
permission-set/policy/assignment apply or teardown, and local profile changes.
After an approved apply, read back permission-set duration/policy, attached policy
lists, exact assignment and creation/provisioning status. Use postflight.py for
runtime SSM expectations. Authenticate strall-dev-plan, verify account/role and
read-only grants, then separately plan the artifact bucket. Do not merge this PR
or claim live readiness from local validation.

## Local evidence (2026-10-09)

Terraform 1.15.2, Terragrunt 0.83.2, AWS provider 6.68.0.
With AWS_CONFIG_DIR=../aws-config, make verify and make test pass: 67 Python
tests, one existing skip. Changed Python Ruff format/lint, Terraform recursive
fmt -check, git diff --check and root Terragrunt HCL validation pass.
scripts/verify.sh --terraform identity-center-permission-set passes disposable
backend-disabled init and Terraform validate. Three mock-provider Terraform plan
tests pass. Exact supplied inline-policy canonical SHA-256:
43f0d7d3f42e95037872b8e90ec11228f2ab869382fdc13c27b493b3e5423d0e.
No live AWS calls, plan/apply, config publication or local AWS profile changes
were performed. All saved-plan/evidence/postflight stages remain pending.
