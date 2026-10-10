# Single-resource IaCPlanReadOnly config-read maintenance

Status: STOP_FOR_HUMAN — genuine human update plan available; seal and separately
approve its exact saved-plan execution. No apply is authorized for the agent.

## Exact delta

Add only ssm:GetParameter's resource
arn:aws:ssm:us-east-1:623155450153:parameter/iac/s3-bucket/iot-digital-twin-artifacts/config
to the existing ReadBindingAndRuntime Resource list. The action set remains the
original 24 actions; no new wildcard, managed policy, KMS permission or unrelated
path is permitted. Permission set IaCPlanReadOnly, PT1H, instance
arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91, and USER
b4486448-d011-7037-9cfb-c16c43f591e1 into account 623155450153 are unchanged.

The original bootstrap declaration and its pinned 24-action policy stay immutable.
The explicit desired maintenance revision is
examples/identity-center-owner.iac-plan-readonly.config-read.json. A strict validator
derives the only permitted delta from the original and requires full equality.
This is a controlled revision of the existing owner's desired policy, not a second
module/deployment owner. No bootstrap behavior or normal agent guard is changed.

## Retained owner and trust boundary

Use the existing applied owner directory:
/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8.
Its local Terraform state, original manifest/postflight, backend/workspace,
provider lock, variable inputs and component snapshots are checked read-only.
The retained owner has exactly the original three resources. Private lineage,
serial and state digest must remain unchanged during planning. There is no init,
remote backend, import/adoption, state repair, module copy or state migration.
Do not duplicate or replay the original create-only bootstrap. Its guards remain.

The explicit HUMAN-only maintenance planner reuses this original owner working
directory and local backend. HUMAN_MAINTENANCE_APPROVED=1 acknowledges use of the
plan-only maintenance control plane, never an apply. AGENT_MODE=1 is rejected,
including with inherited mutation approvals. An owner AdministratorAccess profile
is only used by the human for this narrowly scoped Identity Center maintenance,
never by an agent for ordinary workload planning. The maintenance apply interface requires BOTH HUMAN_MAINTENANCE_APPROVED and
AWS_MUTATION_APPROVED plus an independently recorded review-manifest digest.
It consumes only the saved update plan and never replans or initializes a backend.

## Exact human planning command (not executed by the agent)

```bash
cd /home/ted/dev/aws-iac
AGENT_MODE=0 HUMAN_MAINTENANCE_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/maintain_identity_center.py plan identity-center-permission-set \
  --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8
```

Fresh read-only live discovery verifies owner account/role, the state-owned
permission-set ARN, PT1H, original exact inline policy, no managed policies and
the exact USER assignment. Stop on denied reads, wrong owner or drift. The planner
writes new maintenance variable/plan/log/context/evidence files ONLY beneath the
original owner's maintenance-reviews directory. Original review inputs, manifest,
state and bootstrap variable files are never replaced. Local Terraform plan runs
in the original directory, without target filters or backend initialization.

Require 0 creates, 1 in-place update, 0 deletes, no unrelated drift. Only
aws_ssoadmin_permission_set_inline_policy.inline_policy may update, and its exact
before/after must differ only by the single ARN. Permission set and assignment
must be no-op, with all other inline-policy attributes identical. Unknown update
values, replacements/creates/deletes or other resources stop review. Human review of the genuine saved plan/evidence is required; tests are never
represented as a live IAM update plan. A genuine human plan now exists as recorded
below; the agent does not run or approve its apply.

## Verification and follow-up

Full make verify/test, Python Ruff format/lint, recursive Terraform formatting,
git diff --check and backend-disabled Identity Center validation are required.
Tests prove the action/resource delta, immutable original bootstrap pin, exact
assignment, agent/ack/CLI rejection, strict update scope and no new active owner.
Mock Terraform applies only seed synthetic disposable TEST state; they do not
apply to the retained real state or AWS. State changes or broader live policy
must stop rather than be normalized or repaired manually.

Retain all current resources/state and raw evidence privately. Rollback of any
future grant is a separate approved policy update, not recreation or bootstrap
replay. After separately approved human execution, verify the exact updated
policy and strall-dev-plan config-path read without falling back to Admin. The
aws-config PR #7, SSM publication, workload bucket/Lambda/IoT/DynamoDB/TwinMaker
execution and ZIP upload remain untouched and separately authorized.

## Local validation results

93 Python tests pass with one existing skip; backend-disabled module validation
passes. Six Terraform mock-provider runs pass, including synthetic existing-state
apply followed by the maintenance plan. The actual mock-provider plan output was
inspected and passed the strict maintenance validator: permission set/assignment
no-op, exactly one inline-policy update and no create/delete. Mock evidence is
explicitly synthetic and not evidence of a live IAM update plan. Terraform 1.15.2,
AWS provider 6.68.0. Original real owner was inspected read-only and matched its
human-reviewed manifest/postflight/source. No actual owner state was changed, no
AWS calls or mutations were made, and no human maintenance plan was run by the
agent. The original bootstrap policy/code/guards and aws-config PR #7 are unchanged.
Those initial validation results predated the subsequently generated human plan.

## Genuine maintenance review and sealed apply extension

The human generated maintenance-reviews/config-read-c6887npy inside the original
owner directory. Its genuine plan has zero creates, one inline-policy update and
zero deletes; permission set and USER assignment are no-op. Local read-only
inspection confirmed its recorded state hash still matches the owner. This is
separate from the earlier explicitly synthetic mock evidence.

The human-only seal action validates the original owner, state lineage/serial/hash,
review/evidence digests, repository identity/ancestry, exact declaration/variables,
archived component/provider lock and re-exported binary/JSON equality. It creates
an exclusive read-only maintenance-manifest.json without changing any original
plan/state/review inputs. The manifest hashes owner state/backend/source/lock,
review files and current scripts/declarations. Record its digest independently;
file permissions alone cannot authenticate review. Do not silently reseal changes.

Apply requires the independently supplied digest plus BOTH human acknowledgement
and mutation approval. It fixes profile identity-center-admin and owner account
835990279085, repeats exact scope/source/state checks and live old-policy checks,
and hashes inputs again just before invoking Terraform apply of only the saved
plan from the original owner directory. No init/replan/target/state migration,
bootstrap replay or alternate owner is permitted. Prior attempts, partial failure
or postflight errors stop without retry/rollback. Native saved-plan apply has no
interactive confirmation: flags and independent digest must follow actual review.

Postflight uses read-only Identity Center APIs to verify exact new inline policy,
unchanged 24 actions, exactly one config ARN addition, PT1H, original USER/account
assignment and empty AWS/customer-managed policy lists. A separate restricted-role
STS check and GetParameter version-only probe uses strall-dev-plan in account
623155450153. Success or ParameterNotFound proves authorization; AccessDenied,
wrong role/account or any other error fails postflight. No SSM publication, profile
configuration, SSO login or bucket/Lambda execution is performed. Private apply.log
and post-apply.json record success, partial failure or failed postflight.

## Exact human seal command (prepared, not executed)

```bash
cd /home/ted/dev/aws-iac
AGENT_MODE=0 HUMAN_MAINTENANCE_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/maintain_identity_center.py seal identity-center-permission-set \
  --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 \
  --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/config-read-c6887npy
```

Review the exact plan/evidence/manifest and record the displayed digest OUTSIDE the
bundle. Do not replace that record with a freshly calculated digest before apply.
Only after separate explicit approval of this exact update, personally run:

```bash
AGENT_MODE=0 HUMAN_MAINTENANCE_APPROVED=1 AWS_MUTATION_APPROVED=1 \
AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1 \
EXPECTED_AWS_ACCOUNT=835990279085 \
python3 scripts/maintain_identity_center.py apply identity-center-permission-set \
  --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 \
  --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/config-read-c6887npy \
  --manifest-sha256 "${REVIEWED_MAINTENANCE_SHA256:?Set the independently recorded digest}"
```

Retain the original owner state after execution. Historical bootstrap variables
and manifest remain unchanged; do not replay an old bootstrap or plan a reversal
using the historical declaration. Further maintenance requires its own review.
This implementation task never executes the real seal/apply or changes PR #7.

## Saved-plan apply extension validation

Full make verify/make test pass: 100 Python tests, one existing skip; all six
Terraform mock runs and backend-disabled Identity Center validation pass. Ruff
format/lint, recursive Terraform formatting and diff whitespace pass. Local binary
export of the genuine maintenance plan equals its reviewed JSON and passes the
strict one-update validator. One read-only inspection approval review timed out;
a narrower local Terraform show retry succeeded without AWS calls. No actual
maintenance manifest, apply log, state mutation, IAM apply or SSM write occurred.
The bootstrap implementation/declarations/guards and aws-config PR #7 are unchanged.
