# Human saved-plan workload execution

Scope: only `s3-bucket/iot-digital-twin-artifacts`, account `623155450153`,
region `us-east-1`, environment `dev`, binding `strall-com-dev`, prefix `/iac`.
The normal published SSM declaration is authoritative. No `--plan-config` plan
is eligible. The reviewed result must be exactly six creates, no changes/deletes.

The separate human command seals an existing normal `review.tfplan`; it does not
plan, initialize, publish configuration, or modify AWS. It verifies the restricted
planning identity, normal preflight, archived Terraform source and provider lock,
embedded saved-plan backend, published config snapshot and remote state. A private
bundle retains the binary, rendered JSON, config/binding values and hashes, remote
state identity, source hashes and review evidence. Record its manifest SHA-256
outside that bundle after reviewing the evidence. Sealing does not approve apply.

Apply requires explicit `AGENT_MODE=0`, `AWS_MUTATION_APPROVED=1`, the independently
recorded digest, and verified human profile `strall-dev` in the target account.
The expected human execution role is the previously confirmed SSO
`AdministratorAccess`; it is checked by STS and is never used for planning.
Agents never enable this workflow. Restricted `strall-dev-plan` performs preflight
and state/config reads; the separately verified human profile performs only the
saved-plan Terraform execution. No init, replan, backend migration or new state
owner is permitted. The original initialized S3 backend workspace is retained.
Source, config, binding, state, backend, tools, provider lock, plan and JSON drift
requires renewed planning/review. Terraform additionally checks state freshness
under its backend lock. Do not run concurrent configuration/state changes during
review and execution; this local seal cannot lock SSM publication.

Only the six reviewed resources may be created: bucket, versioning, ownership,
public access block, encryption and runtime parameter. Bucket security values and
the exact reviewed declaration are checked. There are no website, public policy
or lifecycle resources. Read-only postflight checks bucket controls, absence of
website/policy/lifecycle configuration, exact runtime JSON, restricted runtime
read, and the managed-resource set in the same remote state. This verifies this
execution's scope; it is not an account-wide inventory assertion.

An attempted apply is permanently recorded in the private bundle, including
failures and failed postflight. Never retry or roll back automatically. Retain
logs and remote state and obtain a fresh human recovery review. No real workload
apply is authorized by this implementation task. Tests use synthetic plans only.

The binary backend check deliberately supports only Terraform 1.15.2 plan format
v3, using the pinned [Terraform plan schema](https://github.com/hashicorp/terraform/blob/v1.15.2/internal/plans/planproto/planfile.proto).
Unknown encodings/versions fail closed and need a separately reviewed update.
Provider executables and the Terraform executable are also hashed at seal time.

## Human commands

Use Terraform 1.15.2 and the existing initialized normal-plan cache directory.
Do not clean, reinitialize or move that workspace. Authenticate `strall-dev-plan`
for seal and read-only verification; separately authenticate `strall-dev` for the
eventual approved mutation. Both profiles must be available during apply.

```bash
cd /home/ted/dev/aws-iac
umask 077
export AGENT_MODE=0 AWS_PROFILE=strall-dev-plan AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=623155450153 EXPECTED_ENVIRONMENT=dev
export EXPECTED_BINDING=strall-com-dev IAC_PREFIX=/iac
# Set PLAN_DIR to the exact directory containing the reviewed normal review.tfplan.
python3 scripts/workload_saved_plan.py seal s3-bucket iot-digital-twin-artifacts \
  --plan-dir "${PLAN_DIR:?exact reviewed normal plan workspace required}"
```

Review `plan.json`, `context.json`, `snapshot.json`, and `evidence/summary.md` in
the printed private bundle. Independently record the printed manifest digest
outside that directory. Neither seal nor a passing test grants execution approval.
After explicit human approval for this exact six-create bucket plan, the human
may run the separate command below. Supply the externally recorded digest; never
compute it from the potentially changed bundle as part of apply.

```bash
cd /home/ted/dev/aws-iac
umask 077
export AGENT_MODE=0 AWS_PROFILE=strall-dev AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=623155450153 EXPECTED_ENVIRONMENT=dev
export EXPECTED_BINDING=strall-com-dev IAC_PREFIX=/iac
export AWS_MUTATION_APPROVED=1
python3 scripts/workload_saved_plan.py apply s3-bucket iot-digital-twin-artifacts \
  --review-dir "${WORKLOAD_REVIEW_DIR:?use the exact sealed review directory}" \
  --manifest-sha256 "${REVIEWED_WORKLOAD_SHA256:?independently recorded reviewed digest required}"
```

The script checks the human caller first, then uses `strall-dev-plan` for normal
preflight, state/config checks and postflight. It applies the sealed binary with
native Terraform from the original initialized remote backend directory. The log
and postflight result stay private. No Lambda ZIP upload is part of this workflow.
