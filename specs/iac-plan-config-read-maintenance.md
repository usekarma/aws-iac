# Single-resource IaCPlanReadOnly config-read maintenance

Status: observed — human maintenance seal/apply/postflight completed; ready for
human merge review. No further mutation is authorized for the agent.

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
maintenance control plane, never mutation approval by itself. AGENT_MODE=1 is rejected,
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
human-reviewed manifest/postflight/source. The agent only implemented/tested the
path; these initial results predated the genuine human plan and subsequent human
apply. Original bootstrap policy/code/guards and aws-config PR #7 remain unchanged.

## Genuine maintenance review and sealed apply extension

The human generated maintenance-reviews/config-read-c6887npy inside the original
owner directory. Its genuine plan has zero creates, one inline-policy update and
zero deletes; permission set and USER assignment are no-op. Before apply, local read-only inspection confirmed the recorded state hash
matched the owner. The human has now applied the reviewed update successfully;
the same owner remains authoritative with its updated state. This execution is
separate from earlier explicitly synthetic mock evidence.

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

## Historical human seal/apply commands (already executed)

**Do not rerun these commands against the applied review.** They document the
completed human procedure, not a pending action.

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
For this completed execution, the human separately approved the exact saved
update and ran:

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
The agent never executed the real seal/apply. The human execution is now complete;
PR #7 remains unmodified pending this PR reaching main.

## Saved-plan apply extension validation

Full make verify/make test pass: 100 Python tests, one existing skip; all six
Terraform mock runs and backend-disabled Identity Center validation pass. Ruff
format/lint, recursive Terraform formatting and diff whitespace pass. Local binary
export of the genuine maintenance plan equals its reviewed JSON and passes the
strict one-update validator. One read-only inspection approval review timed out;
a narrower local Terraform show retry succeeded without AWS calls. The agent did
not seal/apply during implementation. The subsequent human
maintenance execution is recorded below. Bootstrap logic/declarations/guards and
aws-config PR #7 remain unchanged.

## Completed genuine human maintenance execution

The human supplied successful execution history, corroborated by local retained
manifest/postflight/state records:

```text
genuine same-owner live plan → sealed exact maintenance bundle
  → explicit human mutation approval → exact saved-plan apply
  → read-only postflight success → original retained state remains authoritative
```

- Creates: 0; Changes: 1; Deletes: 0.
- Only changed resource: aws_ssoadmin_permission_set_inline_policy.inline_policy.
- Human-reviewed maintenance manifest SHA-256:
  `11ce404bb2998a75df3e637717e991638880ffefa1cb293a310f89552c78c4b0`.
- Owner profile/account: identity-center-admin / 835990279085.
- Permission set, PT1H and USER b4486448-d011-7037-9cfb-c16c43f591e1 assignment
  into account 623155450153 remained unchanged.
- No AWS managed policies or customer-managed policies were attached.
- The original 24 IAM actions remained unchanged; exactly the single config ARN
  was added to the existing ssm:GetParameter resource list, with no other delta.
- Same retained local state remains authoritative; no second owner, import,
  adoption, state migration or permission-set recreation occurred.
- Read-only postflight returned verified and the workload-role probe reported:
  `GetParameter permitted; ParameterNotFound`.
  This proves authorization succeeded at postflight and the parameter was absent
  then. It does not claim publication or current parameter existence.
- No SSM config publication or artifact-bucket deployment occurred.

The updated retained state policy equals the reviewed maintenance declaration.
The old planning-state digest is historical pre-apply evidence, not the current
applied-state digest. Retain both immutable review inputs and updated owner state;
do not replay seal/apply or replace state with an old snapshot. Only the explicit
human-supplied digest and non-secret summary are committed; raw state/plan/logs and
postflight evidence remain private/untracked.

aws-config PR #7's AccessDenied finding is now historical. Its remaining code/PR
dependency is PR #13 merged with declarative IAM state on main; it remains untouched
until that happens. Later config publication and workload execution still require
separate review/authorization. This documentation finalization changes no policy,
Terraform, maintenance behavior, ownership or safety boundary.

## Documentation finalization verification

The finalization changes only the spec and component README. Full relevant local
checks pass: 100 Python tests with one existing skip, six Terraform mock runs,
backend-disabled Identity Center validation, recursive formatting and diff checks.
Final-head CI is checked separately before human merge review. No policy, source,
state-ownership or safety behavior is changed; no AWS APIs/mutations, publication,
apply or replay are performed during finalization. PR #7 remains untouched.
