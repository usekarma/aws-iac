# Upgrade verification record

Original main inspected: aws-iac 6c127a9; aws-config b39afb8. Existing draft work
extended: aws-iac f678fee; aws-config bd959f7. Template principles inspected at 2c23b89.

## Executed locally

Python 3.12; Ruff 0.11.13; ShellCheck 0.11.0; python-hcl2 7.3.1;
jsonschema 4.23.0; Terraform 1.15.2; Terragrunt 0.83.2.
Verification dependencies are exact-version and wheel-hash locked for Python 3.12/Linux x86_64.

- Both make verify commands passed; aws-config also used AWS_IAC_DIR=../aws-iac.
- IaC: 23 tests passed; 1 config-only test skipped. Config: 18 passed; 4 IaC-only skipped.
- All 20 current component configurations and 4 bindings passed explicit local contracts.
- All tracked/new Python/shell syntax and JSON checked; duplicate keys rejected.
- Changed Python passed Ruff lint/format; changed shell passed ShellCheck.
- All Terraform files passed fmt checks; root Terragrunt fmt/HCL validation passed.
- Local HCL parser checked all modules; duplicate and undefined local references rejected.
- Static security regression inventory passed without added risk patterns.
- Both synthetic make demo runs produced private JSON/Markdown proposals with strong
  destructive approval, persistent-data risk, root-volume risk and preservation caveats.
- Guard tests proved agent mode blocks default apply, destroy, auto-approve, backend
  bootstrap, local state cleanup, AMI build/pruning and image publication before cloud calls.
- Config tests proved inherited acknowledgement does not bypass agent mode, wrong
  accounts/bindings fail, and constrained schemas reject malformed types/unknown keys.
- Postflight tests distinguish absence from permission failures; no mutation commands exist.
- Diff/whitespace and credential-pattern scan passed; no credentials were introduced.

## Provider validation limitation (not success)

Backend-disabled VPC init succeeded and downloaded hashicorp/aws 6.67.0.
Terraform validate could not start that provider: its local Unix socket returned
`socket: operation not permitted`. This is a runtime restriction, confirmed in provider
debug output. No provider validation success is claimed. GitHub CI now also runs
backend-disabled validation of affected components without AWS credentials. Provider
or remote-module failures block that job and must be fixed before accepting a live plan.
No live STS, SSM, inventory, plan, postflight, config publication, apply or destroy ran.
Mocked tests and synthetic plan evidence are labeled; they do not attest current AWS state.

## Compatibility and operational limits

- Human deploy default remains apply, guarded by explicit target/approval variables.
  scripts/plan.sh forces agent mode; read-only IAM is the true authority boundary.
- Agent mode intentionally rejects inherited approval. AMI pruning additionally needs
  AWS_DESTRUCTIVE_APPROVED=1 and typed confirmation; local-state cleanup needs
  LOCAL_STATE_CLEANUP_APPROVED=1. These acknowledgements do not authorize an agent.
- Config publication now requires schema dependencies; unknown top-level keys and
  unresolved same-environment dependencies fail. Extend contracts deliberately for
  new components or external runtime dependencies.
- Two pre-existing semantic defects were repaired: duplicate Grafana runtime local,
  and undefined ECS service config alias. Formatting changes preserve HCL semantics.
- Provider versions/remote-module branches remain unpinned in existing infrastructure.
  Schema/security checks are deliberately limited; they cannot prove IAM least privilege,
  network safety, restoration viability or cost. Full plans can contain secrets.
- Inventory/postflight is selected account/region only and covers a bounded set of
  resource types; application health, S3/database/ECS verification and other regions
  remain per-spec checks. Branch protection needs separate owner configuration.

No AWS resources or existing Terraform state were modified.
