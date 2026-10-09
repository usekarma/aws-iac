# Identity Center permission set component

Creates a configurable Identity Center permission set, its inline policy and
USER/GROUP account assignments. The Identity Center instance, Identity Store and
principals must already exist. No managed policy attachments, instance creation,
user/group creation or Organizations changes are implemented.

The component follows the existing architecture: aws-config declarations are
published to owner-account SSM, the root Terragrunt configuration selects the
component, and runtime metadata is written to SSM. There is no separate IAM CLI
deployment path. The example in this repository is reviewable input, not published
configuration or authorization.

## Reviewed bootstrap flow

```text
verified owner / independently verified delegated-admin context
        ↓
identity-center-permission-set component
        ↓
IaCPlanReadOnly permission set + exact inline policy
        ↓
USER assignment into account 623155450153
        ↓
strall-dev-plan CLI profile
        ↓
read-only artifact-bucket Terraform plan
```

The repository runner currently requires owner account `835990279085` in
`us-east-1`. A different delegated administrator requires independent verification
and a reviewed guard change; a profile name does not establish authority. The
provider also restricts the administration account, and Terraform preconditions
check caller identity and configuration agreement. Backend initialization and
SSM reads through the wrapper happen only after the owner check. Existing binding,
credential, argument-override, agent-mode and backend protections remain active.

Use read-only IAM in the owner context for preflight/planning. An elevated human
owner-context identity is needed only for separately approved administration of
this component. The resulting strall-dev-plan role cannot bootstrap itself, manage
Identity Center, or plan arbitrary account infrastructure: its policy is scoped to
the IoT artifact bucket and its state. Agents keep AGENT_MODE=1 throughout.

## Configuration

SSM input: `/iac/identity-center-permission-set/<nickname>/config` in the owner
account. Fields:

- `administration_account_id`: independently verified administration account.
- `permission_set_name`, `description`, `session_duration`: permission-set inputs.
- `instance_arn`: existing instance; `inline_policy`: IAM policy JSON object.
- `assignments`: list of `target_account_id`, `principal_type` (USER/GROUP), and
  existing `principal_id`. Duplicate account/type/principal entries are rejected
  by Terraform's stable-key map.
- Optional `project` and `tags`: normal Project/Component tagging conventions.

The exact reviewed declaration is
[identity-center-owner.iac-plan-readonly.json](../../examples/identity-center-owner.iac-plan-readonly.json).
It retains the human-supplied policy exactly, including string/list Action forms.
The reusable Terraform resources contain no hard-coded permission-set name or
assignment principal. Inline policy provisioning precedes account assignment.

Runtime SSM contains permission_set_arn, instance_arn and assignments. Output:
permission_set_arn. The reviewed instance has IdentityStoreId `d-9067ccec40`;
assignment APIs use principal IDs, so the module does not manage/read that store.

## Live prerequisites and commands

No verified local administration profile exists. The owner-account binding,
configuration publication and backend existence have not been verified. Do not
reuse strall-dev's binding or invent an owner environment. A separate reviewed
aws-config change must supply the component schema/config and the actual owner
binding before publication; nothing is published by this PR.

After those prerequisites are supplied, set the independently verified profile,
environment and binding and run the standard wrapper:

```bash
export AGENT_MODE=1 AWS_REGION=us-east-1 EXPECTED_AWS_ACCOUNT=835990279085
export IAC_PREFIX=/iac
: "${AWS_PROFILE:?Set the verified owner-context read-only profile}"
: "${EXPECTED_ENVIRONMENT:?Set the verified owner environment}"
: "${EXPECTED_BINDING:?Set the exact owner binding}"
bash scripts/plan.sh identity-center-permission-set owner-iac-plan-readonly
```

Expected resources are listed in the [spec](../../specs/iac-plan-readonly.md).
Inspect existing permission sets/assignments before planning; a name collision
requires a separate reviewed adoption/state-repair task, not duplicate creation.
Never bootstrap backend infrastructure during planning. No current live plan or
apply is authorized. Publication, IAM apply and any teardown require explicit
human approval of their exact targets and current plans.

## Local checks

```bash
export AGENT_MODE=1 AWS_CONFIG_DIR=../aws-config
. .venv/bin/activate
make verify
make test
bash scripts/verify.sh --terraform identity-center-permission-set
```

Run `terraform test` from a disposable backend-disabled component copy with
`examples/identity-center-owner.iac-plan-readonly.json` preserved two levels above
the component, matching the repository layout. All Terraform tests use a mock
provider and `command = plan`; they perform no AWS operations.

## Proposed planning profile

After separately approved provisioning/assignment, the human adds:

```ini
[profile strall-dev-plan]
sso_start_url = https://d-9067ccec40.awsapps.com/start
sso_region = us-east-1
sso_account_id = 623155450153
sso_role_name = IaCPlanReadOnly
region = us-east-1
output = json
```

Then run `aws sso login --profile strall-dev-plan` and explicit-region STS identity
verification. Require account `623155450153` and the
`AWSReservedSSO_IaCPlanReadOnly_<suffix>` role. Do not substitute AdministratorAccess.
