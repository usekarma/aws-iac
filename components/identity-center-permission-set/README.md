# Identity Center permission sets and human bootstrap

The reusable component manages a permission set, inline policy and stable-key
USER/GROUP assignments. Instance, Identity Store and principals already exist.
No managed policy attachments, SSM runtime resources or user/group creation are
needed. The normal SSM-configured component and Terragrunt path remain available.

## Two separate trust boundaries

```text
HUMAN BOOTSTRAP CONTROL PLANE
human + verified owner AdministratorAccess
  → reviewed local declaration → private local-backend bootstrap plan
  → human review → separately approved future execution

NORMAL AGENT WORKFLOW
restricted planning identity → normal preflight/config/SSM → plan
  → human-approved mutation path
```

AdministratorAccess is acceptable only for the one-time HUMAN bootstrap of
IaCPlanReadOnly. Agents never use this bootstrap path. An agent must not unset
AGENT_MODE or set human approval flags to run it. AGENTS.md remains unchanged.
The ordinary planning role still needs read-only IAM; it cannot bootstrap itself.
The reviewed strall-dev-plan policy is scoped to the artifact-bucket workload;
it is not permission to administer or plan Identity Center infrastructure.

## Human bootstrap plan command

Run personally from the repository root, after reviewing the declaration/code:

```bash
AGENT_MODE=0 HUMAN_BOOTSTRAP_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/bootstrap_identity_center.py plan identity-center-permission-set
```

HUMAN_BOOTSTRAP_APPROVED acknowledges use of this human-only path. It is **not**
Terraform apply approval. The entrypoint accepts only `plan` and this component;
apply/destroy/other components/extra options are rejected. Inherited
AWS_MUTATION_APPROVED does not enable an apply command. No bootstrap apply path
is implemented in this PR: it stops at plan review. Eventual execution needs a
separately reviewed human path and AWS_MUTATION_APPROVED=1 after actual approval.
No single flag may authorize both bootstrap entry and mutation.

The planner:

1. Rejects agent mode, missing human acknowledgement, incorrect expected owner/
   region, competing credentials and Terraform argument overrides before AWS.
2. Verifies STS account 835990279085 and the owner AdministratorAccess role.
3. Verifies the existing instance/owner and reads every permission-set name.
   AdministratorAccess must exist; IaCPlanReadOnly must not. Any denied read stops.
4. Reads only the checked-in
   [reviewed declaration](../../examples/identity-center-owner.iac-plan-readonly.json),
   and verifies the exact identity, assignment, PT1H and policy digest.
5. Copies the same Terraform resource definitions into a private snapshot under
   ignored `artifacts/identity-center-bootstrap/review-*`. A snapshot-only
   bootstrap_override.tf selects the local backend; normal source/backend is
   unchanged. This uses Terraform's documented
   [backend override semantics](https://developer.hashicorp.com/terraform/language/files/override#merging-terraform-blocks).
6. Runs init/validate/plan only, with local state, input=false and lock=false.
   No remote backend creation/update or SSM reads/publication occur.
7. Exports private plan JSON and rejects anything except exactly three creates
   with the reviewed instance, policy and USER/account assignment. It invokes
   scripts/evidence.py's generator to produce value-free review evidence and
   saved-plan digests. Raw output stays in the private terraform.log/plan.json.

No `/iac/environment`, config publication or SSM framework prerequisite is
created to make this work. No AWS mutation is performed by bootstrap planning.
A bootstrap failure is not evidence that a resource is absent. Inspect the exact
private error before expanding any permissions. The live planner is for the
human to run; agents validate it only through mocks.

## State ownership and eventual execution

Expected managed resources: permission set, inline policy and one USER assignment.
Local state/plan/snapshot/lock file belong to the human bootstrap review directory;
retain them securely. Do not delete these artifacts as cleanup after any eventual
apply. Do not run the normal remote-state unit against the same permission set:
that is a second independent state owner and could propose duplicate creation.
Any adoption or backend/state migration needs a separate reviewed task; no state
repair/import/migration is implemented here. A changed declaration/source/identity
or stale plan requires fresh review. Once IaCPlanReadOnly exists, the bootstrap
planner stops instead of preparing duplicate resources.

## Normal configuration path

Default input remains `/iac/identity-center-permission-set/<nickname>/config`.
Fields: administration_account_id, permission_set_name, description,
session_duration, instance_arn, inline_policy (JSON object), assignments (list of
account/type/principal), plus optional project/tags. The provider restricts the
administration account; caller/configuration preconditions remain. Inline policy
provisioning precedes assignment. Output: permission_set_arn.

bootstrap_config_json is an input mechanism used by the human planner, not an
approval mechanism. Normal scripts expose no bootstrap option, reject TF_VAR/CLI
argument overrides and still require their actual owner binding/published config
and existing remote backend. Other components are unaffected.

## Local validation

```bash
export AGENT_MODE=1 AWS_CONFIG_DIR=../aws-config
. .venv/bin/activate
make verify
make test
bash scripts/verify.sh --terraform identity-center-permission-set
```

Terraform mock tests exercise both SSM and local declaration paths, wrong-account
preconditions and the absence of bootstrap SSM reads. Run them in a disposable
component copy preserving the repository's component/examples directory layout.
No actual human bootstrap or AWS call is run by tests.

## After separately approved provisioning

Verify the exact inline policy, absence of managed-policy attachments, assignment
provisioning status and the USER/account association. The human then adds:

```ini
[profile strall-dev-plan]
sso_start_url = https://d-9067ccec40.awsapps.com/start
sso_region = us-east-1
sso_account_id = 623155450153
sso_role_name = IaCPlanReadOnly
region = us-east-1
output = json
```

Authenticate with aws sso login --profile strall-dev-plan and explicit-region STS.
Require account 623155450153 and AWSReservedSSO_IaCPlanReadOnly_<suffix>. Normal
agent workload planning then uses this restricted role, normal binding/config
checks and existing backend safeguards. No profile edits occur in this PR.
