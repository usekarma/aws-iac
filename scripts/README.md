# Repository commands

See [the root README](../README.md) for required versions and expected target variables.

| Command | Behavior |
| --- | --- |
| `./scripts/verify.sh` | No AWS calls; required local/CI checks |
| `./scripts/verify.sh --terraform COMPONENT` | Additional backend-disabled provider validation in disposable copy |
| `./scripts/preflight.sh` | Read-only STS account and SSM binding checks |
| `./scripts/plan.sh COMPONENT NICKNAME` | Private saved plan; no backend creation/update |
| `./scripts/plan.sh COMPONENT NICKNAME --destroy` | Private destroy proposal; no execution |
| `./scripts/inventory.sh` | Read-only account-wide billable-resource metadata |
| `./scripts/deploy.sh --plan COMPONENT NICKNAME` | Same safe plan path |
| `./scripts/deploy.sh --validate COMPONENT NICKNAME` | Remote-backend-aware validation; use local verification for offline work |
| `./scripts/deploy.sh COMPONENT NICKNAME` | APPLY; explicit human approval required |
| `./scripts/deploy.sh COMPONENT NICKNAME -d` | DESTROY; explicit human approval required |
| `./scripts/bootstrap/remote_state.sh` | S3/DynamoDB mutation; explicit human approval and binding required |
| `./scripts/clean.sh` | Deletes local artifacts including state files; not cloud cleanup |

Mutation entrypoints require AWS_MUTATION_APPROVED=1 after actual human approval.
`--auto-approve` is permitted only for approved apply/destroy, never planning/validation.
Saved plan execution requires approval too. Plans are sensitive and use -lock=false
for read-only planning; coordinate with operators and regenerate if state/config changes.
The existing module state bucket/lock table must already exist; backend provisioning
is a separate approved task. No check here authorizes an agent to mutate AWS.

Use make verify/test/demo and read ../docs/evidence-and-evaluation.md for the enforced agent-safe workflow.
