# AWS infrastructure as code

Reusable Terraform components orchestrated by Terragrunt, with deployment inputs
and runtime dependency metadata in AWS Systems Manager Parameter Store.
Part of [Adage](https://github.com/usekarma/adage).

## Repository map

- `components/`: VPC, ECS, ClickHouse/MongoDB/Redpanda stack, Cognito, DNS,
  S3, Lambda, serverless API/site, Grafana and other modules. email-forwarding is
  an incomplete prototype, explicitly blocked from deployment. Some directories
  (e.g. rds-postgres, eks-cluster, sqs-queue) contain documentation only.
- `terragrunt.hcl`: per-account S3 state, DynamoDB locking, component/nickname inputs.
- `scripts/deploy.sh`: existing single-component runner; defaults to **apply**.
- `AGENTS.md`, `specs/`, `docs/`: authority boundaries, work specs and runbooks.
- `scripts/verify.sh`, `tests/`, `.github/workflows/verify.yml`: non-destructive gates.

[`aws-config`](https://github.com/usekarma/aws-config) owns environment bindings
and `iac/<environment>/<component>/<nickname>/config.json`. Its publishers write
SSM `${IAC_PREFIX:-/iac}/environment` and `/<component>/<nickname>/config`.
Terraform reads those inputs and publishes `/runtime` dependency metadata.
Config existence is a prerequisite, **not** approval or enforcement of Git review.
The current runner does not enforce the binding's strict/branch/drift metadata.

## Safe change workflow

SPEC → inspect → implement → verify → plan → review plan → **human approval** →
apply/destroy → postflight verification → operational observation.

Read [AGENTS.md](AGENTS.md) and [the workflow](docs/agent-workflow.md). Copy
[specs/TEMPLATE.md](specs/TEMPLATE.md) for substantive infrastructure work; small
documentation changes can record scope and verification in a PR description.
Keep production/non-production changes separate. Never manually alter state as cleanup.

Prerequisites: Bash, Git, Python 3.12+, hash-locked verification tools, Terraform 1.15.2,
Terragrunt 0.83.2. Verification requires no AWS credentials:

```bash
./scripts/verify.sh
./scripts/verify.sh --terraform clickhouse
```

The first command checks syntax, changed-file formatting/lint, JSON, credential
patterns and mocked safety tests. The second also downloads providers and validates
that module in a disposable copy with its backend disabled. Network/provider failures
are reported, never treated as success. Existing unchanged Terraform formatting debt
is reported separately; new edits must meet the checks.

## Target and plan

Confirm these values independently; account/profile names are local conventions.
Do not infer environment from nickname: ClickHouse `usekarma-dev` is configured in prod.

```bash
export AWS_PROFILE=prod-karma
export AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT='<confirmed-12-digit-account-id>'
export EXPECTED_ENVIRONMENT=prod
export EXPECTED_BINDING=usekarma-dev-prod
./scripts/preflight.sh
./scripts/plan.sh clickhouse usekarma-dev
# Prepare a teardown proposal only:
./scripts/plan.sh clickhouse usekarma-dev --destroy
```

Preflight checks STS identity and exact SSM binding. Planning requires an existing
state bucket/lock table and disables Terragrunt backend bootstrap/updates. Plans use
`-lock=false` with read-only IAM; avoid concurrent deployments and regenerate stale
plans. The private `review.tfplan` lives inside the Terragrunt cache below
`.terragrunt-work/<account-id>/<component>/<nickname>/`. Inspect it there with
`terraform show review.tfplan`; record its `sha256sum`. Plans can contain secrets.
Never commit or publish them or their JSON/text output.

## Approved execution only

The existing apply/destroy CLI remains available, but now requires verified expected
target variables and `AWS_MUTATION_APPROVED=1`, set by the operator **after explicit
human approval**. The acknowledgement cannot authorize an agent. `--auto-approve`
is rejected for planning/validation. Apply/destroy retain native confirmation unless
the approved operator explicitly selects that flag. The runner regenerates a plan on
apply/destroy: review it again at the native prompt, and stop if it differs from the
approved scope. Prefer executing the exact approved saved plan from its cache through
Terraform after rerunning preflight; this is a separately approved mutation, not an
autonomous agent command. Saved plans execute without an additional confirmation prompt.

Backend bootstrapping with `scripts/bootstrap/remote_state.sh` also requires approval
and preflight. It can create/update S3/DynamoDB and retention rules. Neither verification
nor planning bootstraps a backend. Approval must cover all resource/data consequences.

## Teardown and postflight

Read [the destructive-operation policy](docs/destructive-operations.md) and
[the ClickHouse cleanup example](specs/clickhouse-cleanup.example.md). ClickHouse
owns MongoDB/Redpanda and data EBS volumes too. `ch-down.sh` additionally tears down
shared VPC/ECS; do not use it for component-only cleanup. `scripts/clean.sh` removes
local artifacts including local state files; do not run it casually.

`./scripts/inventory.sh` performs read-only account-wide EC2/EBS, ALB, NAT, EIP,
snapshot and AMI inventory. Compare exact preflight IDs with the reviewed plan,
prove preserved objects survive, and investigate leftovers without deleting them.
Check ECS, DNS, SSM and S3 backups as relevant; observe service health and cost after
approved changes. See the workflow for operational readiness and known limitations.

CI runs the same local gate on PRs/pushes with no AWS credentials or deployment steps.
Require its status via GitHub branch protection separately. Do not interpret green
syntax/tests as a valid live plan or production readiness.

## Agent-first commands and evidence

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
export AGENT_MODE=1
make verify
make test
make demo
```

The lock targets Python 3.12/Linux x86_64. Terraform/Terragrunt remain separate
prerequisites in aws-iac. Agent mode blocks mutation even with inherited approval.
The legacy deploy default remains apply for human compatibility; agents use explicit
planning/validation. See [architecture assessment](docs/architecture-assessment.md)
and [evidence, postflight and metrics](docs/evidence-and-evaluation.md).
Raw plans and generated evidence belong in ignored artifacts/ or another private path.
