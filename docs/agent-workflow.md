# Agent workflow and operational readiness

`aws-config` stores `account_environments/<binding>.json` and
`iac/<environment>/<component>/<nickname>/config.json`. Its publishers **write SSM**.
`aws-iac` contains Terraform under `components/` and one root `terragrunt.hcl`.
Config lives at `${IAC_PREFIX:-/iac}/<component>/<nickname>/config`; Terraform
publishes dependency metadata under the corresponding `/runtime` path. These are
runtime dependencies via SSM, not Terraform remote-state dependencies.

Some modules also declare a us-east-1 provider alias; include every affected region
in the spec and review the plan rather than assuming the selected primary region
covers all resources.

State uses `<account-id>-tf-state`, `<account-id>-tf-locks`, and
`<component>/<nickname>/terraform.tfstate`; work directories live at
`.terragrunt-work/<account-id>/<component>/<nickname>/`. CLI profile names are local
aliases, not an authoritative account map. Binding files do not contain account IDs.
`usekarma-dev` is a nickname; its ClickHouse config is in **prod**. Confirm the
actual binding, account ID and region before planning or changing anything.

## Lifecycle

| Stage | Evidence | Authority |
| --- | --- | --- |
| Spec and inspect | Goal, targets, preservation list, code/config revisions | Agent |
| Implement and verify | Minimal diff, deterministic checks, failure cases | Agent |
| Preflight and plan | Exact identity/binding, reviewed change list and private plan | Agent with read-only credentials |
| Review | Security, cost, persistent data, recovery and blast radius | Agent prepares; human decides |
| Apply/destroy or publish SSM | Concrete operation and current plan/config approved | Explicit human approval |
| Postflight and observe | Read-only resource checks, health/cost/error observations | Agent |

For small documentation edits, a PR description with goal, scope and verification
is enough. Use specs/TEMPLATE.md for resource/security/cost/migration work.
The teardown example is a proposal, not authorization or evidence of current AWS state.
Reconcile current inventory before reusing it.

## Read-only preflight

Supply values independently confirmed with the owner/account inventory, not guessed:

```bash
export AWS_PROFILE=prod-karma
export AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT='<confirmed-12-digit-account-id>'
export EXPECTED_ENVIRONMENT=prod
export EXPECTED_BINDING=usekarma-dev-prod
./scripts/preflight.sh
```

Preflight rejects competing credential sources, checks STS and exact SSM binding,
and does not print SSM content. SDK operations use explicit region/profile.
Environment creation cannot pass the existing-binding check: review the local
binding file and use the config publisher's bootstrap identity guard instead.
Preflight verifies the selected region and the binding in that region; it cannot
prove an operator supplied the correct expected region. The spec is that source.

## Verification prerequisites and gates

Both repos: Bash, Git, Python 3.12+, ShellCheck 0.11.0.
IaC additionally: Terraform 1.15.2 and Terragrunt 0.83.2 (the existing CLI convention).
`./scripts/verify.sh` performs no AWS calls and makes no Terraform state changes.
It checks all tracked shell/Python syntax, all JSON (duplicate keys rejected), changed
shell scripts with ShellCheck, obvious credential material, and behavioral safety tests.
IaC checks Terraform syntax everywhere using non-writing fmt checks, enforces formatting
on changed Terraform files, and validates/formats the root Terragrunt config.
Legacy unchanged Terraform formatting differences are reported, not silently reformatted.
Use VERIFY_BASE_REF to set the comparison base; default is origin/main, including local
uncommitted/untracked edits. CI uses the PR base commit. An invalid base is a failure.
Do not move the base to hide a changed-file failure.

IaC provider validation: `./scripts/verify.sh --terraform clickhouse` (or another
component; `all` checks every component containing Terraform). This copies the module
to a temporary directory and runs `terraform init -backend=false` then `terraform validate`.
It needs registry network access; failures block the affected module. It does not read
live SSM or initialize remote state. Terraform providers are not currently version/lock
pinned by the existing modules; results may vary after provider upgrades.

Config checks binding field types, environment selection, config object structure,
tags and duplicate keys. `AWS_IAC_DIR=../aws-iac ./scripts/verify.sh` additionally checks
that config component names exist in the sibling checkout. This is structural validation,
not a complete schema for every module's optional inputs. Deployment scripts need boto3.

The credential scan covers private-key markers and common AWS/GitHub token patterns;
it is not a complete security audit. Review IAM, CIDRs, secrets and template changes manually.
The IaC wrapper runs one Terragrunt unit: the former --all mode could add
auto-approval implicitly. It no longer forces non-interactive mutation execution.
CI needs no cloud credentials and cannot apply/destroy or publish SSM. Branch protection
must separately require the verification check; workflow files do not enforce review.

## Production readiness and recovery

For each relevant change record owner, logs and retention, metrics and alarms,
health checks, rollback/restore procedure, tags, hourly cost and cleanup date,
least-privilege IAM, network ingress/egress, encryption, secret source/rotation,
backup location/age and restoration evidence. Use N/A when justified; do not retrofit
irrelevant monitoring into every module. Record prototype shortcuts with risk, owner
and expiry. Production promotion needs those gaps resolved and human approval.
Restore a previous Git/SSM config version only after review; create a fresh plan.
Redeployment restores resources, not deleted data. Never restore remote Terraform
state just to reverse a deployment. Treat state repair as a separate approved task.

## Existing issues to address separately

- Modules have no provider version constraints or committed provider lock files.
- Grafana provider validation is blocked by a pre-existing duplicate runtime_path local
  in header.tf and main.tf. Its invalid one-line HCL blocks were repaired here;
  resolve the remaining semantic error in a separate module-focused change.
- Some legacy Terraform/shell files need formatting/lint remediation in scoped changes.
- Config binding `iac_strict`, branch and allow_drift fields are metadata; current
  deployment scripts do not enforce Git revision/review policy.
- ClickHouse runtime/userdata includes MongoDB connection details. Handle all
  plan/state/runtime artifacts as sensitive; review secret handling separately.
- `ch-down.sh` chains broad teardown including shared VPC/ECS. Do not use it for
  component-only cleanup. `clean.sh` removes local state artifacts, not AWS resources.
