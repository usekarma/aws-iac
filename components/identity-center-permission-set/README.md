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
Terraform apply approval. Only this component supports the explicit `plan`, `seal`
and saved-plan `apply` actions. Destroy, other components and extra Terraform
arguments are rejected. Apply requires BOTH HUMAN_BOOTSTRAP_APPROVED=1 and
AWS_MUTATION_APPROVED=1 after actual human approval, plus the independently recorded
review-manifest digest. No single flag authorizes both bootstrap entry and mutation.

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

## Human seal/apply procedure (completed for this instance)

```text
human bootstrap plan → saved review bundle → seal exact inputs
  → human reviews plan and records manifest SHA-256 outside the bundle
  → separate AWS_MUTATION_APPROVED=1 approval → apply exact saved tfplan
  → read-only post-apply verification → bootstrap ends
```

The bundle `artifacts/identity-center-bootstrap/review-uhd86fs8` has already been
sealed and successfully applied by the human. **Do not rerun the commands below
against that applied bundle.** They document the human procedure, not a pending
action. For an eligible unapplied bundle, sealing is LOCAL and non-mutating and
never regenerates or replaces review.tfplan, plan.json or evidence:

```bash
AGENT_MODE=0 HUMAN_BOOTSTRAP_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/bootstrap_identity_center.py seal identity-center-permission-set \
  --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8
```

Seal verifies original evidence digests, context/component identity, commit
ancestry, checked-in component/declaration equality, provider lock/local-backend
metadata and source archived inside the saved plan. It re-exports the binary plan
with `terraform show` and requires exact equality with the reviewed JSON, its
variables and the three-create policy/assignment scope. It creates a new manifest
exclusively, marks it read-only and records SHA-256 for the binary, JSON, context,
evidence, component snapshots, variable inputs, local-backend metadata, lock file
and relevant checked-in scripts/declaration. Existing manifests are never replaced.

Record the displayed manifest digest separately after review. File permissions
alone are not tamper-proof: apply requires the external reviewed digest, so do not
calculate a new digest from potentially changed files just before apply. Changed
inputs require fresh review; never silently reseal to bypass rejection.

For an eligible unapplied bundle ONLY after explicit human approval of its exact
saved plan, set its recorded REVIEWED_MANIFEST_SHA256 and personally run. The
following command was already executed successfully for the displayed bundle:

```bash
AGENT_MODE=0 HUMAN_BOOTSTRAP_APPROVED=1 AWS_MUTATION_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/bootstrap_identity_center.py apply identity-center-permission-set \
  --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 \
  --manifest-sha256 "${REVIEWED_MANIFEST_SHA256:?Set the independently reviewed digest}"
```

Apply rejects arbitrary plan paths, missing/tampered files, component/config/script
changes, new state/workspace overrides and every non-create/unexpected resource.
It checks STS and instance/permission-set names again; existing IaCPlanReadOnly
stops stale-plan execution. It repeats hashes just before mutation, then invokes
only `terraform apply -input=false -no-color review.tfplan` in the reviewed
snapshot. No init, plan regeneration, auto-approve or AWS write precedes apply.
Saved-plan execution has no native confirmation prompt: the two approvals and
external digest are the human execution boundary.

After success, read-only APIs verify PT1H, exact policy, empty AWS/customer-managed
policy attachment lists and the exact USER/account assignment. Private apply.log
and post-apply.json record the result. Verification failure is reported as failure
after mutation, never rolled back or retried automatically. A partial apply requires
state/log inspection and a separately reviewed recovery operation. No CLI profile
edit, SSO login, artifact upload or normal workflow is triggered.

## Retained bootstrap state ownership

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

## Completed bootstrap result

The verified human execution used identity-center-admin in owner account
835990279085, a sealed three-create saved plan, separate explicit apply approval,
and successful read-only postflight. That bootstrap created IaCPlanReadOnly with
the initial reviewed inline policy and USER assignment into 623155450153. The
separately approved maintenance below records its later single-resource revision.
No managed policies are attached. Local bootstrap state remains private and must be retained.
The execution manifest digest is recorded in the spec at the human's request.

The CLI profile was configured separately afterward. strall-dev-plan successfully
planned PR #11's artifact bucket using account 623155450153 and
AWSReservedSSO_IaCPlanReadOnly_92e4b2f1ca02a611: six creates, no changes/deletes.
The bootstrap script did not configure profiles or perform workload planning.
Agents continue using restricted IAM for ordinary planning; no additional apply,
role/policy modification or state migration is authorized by merge review.

## Completed existing-owner config-read maintenance

The single config-path GetParameter resource grant has now been applied by the
human using the genuine sealed maintenance plan. Its desired state is recorded as a
separate reviewed maintenance declaration and HUMAN-only plan/seal/saved-plan
apply interface. It retains the bootstrap state owner in place, never replays
create-only bootstrap or initializes another backend, and requires separate
mutation approval plus the independently recorded maintenance manifest digest. See
[maintenance scope and human command](../../specs/iac-plan-config-read-maintenance.md).
The original bootstrap policy/guards remain pinned. Normal agents retain their
restricted planning role. Execution was 0 creates, 1 inline-policy update, 0 deletes;
PT1H/permission set/USER assignment and the original 24 actions remain unchanged.
No second state owner or managed-policy attachment was created. Read-only postflight
verified the exact delta and reported GetParameter permitted; ParameterNotFound
for strall-dev-plan. This proves config-read authorization, not publication or
parameter existence. No SSM config was published or artifact bucket deployed.
Retain the updated original state and do not replay the historical seal/apply.
