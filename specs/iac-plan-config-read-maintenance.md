# Single-resource IaCPlanReadOnly config-read maintenance

Status: STOP_FOR_HUMAN — local implementation validated; live human update plan
must be generated before any execution approval. No AWS mutation is authorized.

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
never by an agent for ordinary workload planning. No maintenance apply interface
is implemented. Any later update execution requires separate reviewed integrity,
state ownership, current plan and explicit human mutation approval.

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
values, replacements/creates/deletes or other resources stop review. Human review
of the genuine saved plan/evidence is required; tests are never represented as a
live IAM update plan. Agent implementation stops with this command pending.

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
