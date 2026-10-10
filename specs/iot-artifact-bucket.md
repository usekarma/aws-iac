# IoT prototype artifact bucket

Status: awaiting human plan review — dedicated read-only identity verified; no apply authorized.
Owner/reviewer: strall / requesting human.

## Goal and scope

Prepare a dedicated non-production Lambda artifact bucket using the existing
`s3-bucket` component. No upload, Lambda deployment, config publication, website,
public policy, lifecycle expiration, apply, destroy or production work is authorized.
Do not modify aws-config or aws-lambda. Preserve the state bucket and all old
artifact versions. No shared-module refactor or new bucket implementation is needed.

## Exact target

- Planning profile: `strall-dev-plan`; account: `623155450153`; region: `us-east-1`.
- Environment: `dev`; binding: `strall-com-dev`; prefix: `/iac`.
- Component/nickname: `s3-bucket` / `iot-digital-twin-artifacts`.
- Bucket: `623155450153-iot-digital-twin-artifacts`.
- State: `623155450153-tf-state`, key
  `s3-bucket/iot-digital-twin-artifacts/terraform.tfstate`.
- Existing backend lock table: `623155450153-tf-locks`; never bootstrap it.

STS and a value-filtered read of `/iac/environment` confirmed account and dev
binding on 2026-10-09. The initial strall-dev SSO session was AdministratorAccess and was forbidden
for planning. After the separately executed human bootstrap, the dedicated
`strall-dev-plan` profile uses `IaCPlanReadOnly`. Use only that restricted profile
for this proposal. No IAM mutation is authorized by the artifact-bucket task.

## Exact expected plan

Only these six resource addresses may have action `create`:

1. `aws_s3_bucket.s3_bucket`
2. `aws_s3_bucket_versioning.versioning`
3. `aws_s3_bucket_ownership_controls.ownership[0]`
4. `aws_s3_bucket_public_access_block.block[0]`
5. `aws_s3_bucket_server_side_encryption_configuration.sse[0]`
6. `aws_ssm_parameter.runtime` — `/iac/s3-bucket/iot-digital-twin-artifacts/runtime`

Expected summary: 6 add, 0 change, 0 destroy. No config SSM parameter is created.
Runtime SSM creation is an expected supporting resource in the future proposal;
no PutParameter is called by planning. No additional resources, replacements,
updates, deletes or drift are acceptable without renewed review.

## Configuration and implementation

`examples/iot-artifact-bucket.strall-dev.json` is a real target proposal, not
published configuration or deployment approval. It enables versioning, AES256
SSE-S3, all four public-access blocks and BucketOwnerEnforced ownership. It sets
force_destroy=false, retains all versions, and uses Project, Component,
Environment, Owner and Purpose tags. The generic component has no website,
public bucket policy or lifecycle rule. Empty storage incurs no object-storage
cost; retained uploaded versions would incur storage charges after a separately
authorized publication. Prototype logging, alarms and restore drills are deferred;
no object data exists as a result of this plan-only task.

`--plan-config` accepts unpublished JSON only for s3-bucket creation plans. It
preserves identity/binding preflight, backend guards, lock=false and agent mode.
Existing callers still read SSM by default; a moved data address preserves that
path. The Terraform variable is an input mechanism, not an IAM safety boundary.
A saved proposal is not approved for execution. Before eventual deployment,
separately review aws-config publication and regenerate a plan using published
SSM config with no override; any change requires new review and human approval.

## Planning identity permissions

Grant only these read actions, scoped to the indicated resources where supported.
Deny infrastructure writes in the permission set; no write permissions are needed
for init/plan with backend bootstrap disabled and lock=false. SSO login itself
is a human authentication prerequisite, not an infrastructure permission grant.

- `sts:GetCallerIdentity` (resource `*`): explicit identity and SDK account checks.
- `ssm:GetParameter`: binding `/iac/environment` and, when refreshing existing
  state, `/iac/s3-bucket/iot-digital-twin-artifacts/runtime`. The proposal override
  does not read the config path. Normal future plans also need GetParameter on
  `/iac/s3-bucket/iot-digital-twin-artifacts/config`.
- `ssm:ListTagsForResource`: the exact runtime parameter if already managed.
- `ssm:DescribeParameters` (resource `*`): the provider reads runtime parameter
  metadata with a name filter when refreshing existing state.
- `s3:ListBucket`, `s3:GetBucketVersioning`: backend bucket
  `arn:aws:s3:::623155450153-tf-state` (HeadBucket, state/workspace listing and
  versioning inspection). Restrict listing prefixes to the target state key and
  Terraform workspace prefix if the backend requests it.
- `s3:GetObject`: only
  `arn:aws:s3:::623155450153-tf-state/s3-bucket/iot-digital-twin-artifacts/terraform.tfstate`.
  No PutObject, DeleteObject, state lock writes or artifact object access needed.
- `dynamodb:DescribeTable`, `dynamodb:GetItem`: `arn:aws:dynamodb:us-east-1:623155450153:table/623155450153-tf-locks`.
  DescribeTable verifies the backend; GetItem reads Terraform state digest
  metadata even with lock=false. No PutItem/DeleteItem is needed.
- On `arn:aws:s3:::623155450153-iot-digital-twin-artifacts`, for refresh if
  resources are already managed: `s3:ListBucket`, `s3:GetBucketLocation`,
  `s3:GetBucketTagging`, `s3:GetBucketAcl`, `s3:GetBucketCors`,
  `s3:GetBucketWebsite`, `s3:GetBucketVersioning`, `s3:GetBucketLogging`,
  `s3:GetBucketRequestPayment`, `s3:GetAccelerateConfiguration`,
  `s3:GetBucketPolicy`, `s3:GetBucketObjectLockConfiguration`,
  `s3:GetReplicationConfiguration`, `s3:GetLifecycleConfiguration`,
  `s3:GetEncryptionConfiguration`, `s3:GetBucketPublicAccessBlock`,
  `s3:GetBucketOwnershipControls`.

If the existing state object uses a customer-managed KMS key, additionally grant
`kms:Decrypt` on that independently verified key only; no key ARN is assumed here.
Backend encryption and live state contents were not inspected after the stop
instruction, so this conditional requirement cannot yet be resolved.

Sources inspected: AWS provider v6.68.0
[`bucket.go`](https://github.com/hashicorp/terraform-provider-aws/blob/v6.68.0/internal/service/s3/bucket.go),
[`parameter.go`](https://github.com/hashicorp/terraform-provider-aws/blob/v6.68.0/internal/service/ssm/parameter.go),
and Terragrunt v0.83.2
[`client.go`](https://github.com/gruntwork-io/terragrunt/blob/v0.83.2/internal/remotestate/backend/s3/client.go).
S3 API GetBucketEncryption maps to IAM s3:GetEncryptionConfiguration;
HeadBucket maps to s3:ListBucket.

These are the bounded permissions for this component/backend, not an account-wide
ReadOnlyAccess recommendation. Provider/Terragrunt versions are not dependency
pinned by the repository; denied reads must be investigated and documented,
never worked around by switching to AdministratorAccess.

## Verification and pending live evidence

Run make verify, make test, Ruff format/lint for changed Python,
terraform fmt -check -recursive, git diff --check, and
bash scripts/verify.sh --terraform s3-bucket. Terraform mock-provider tests
exercise proposal security settings and the existing SSM input path without AWS.
Record actual command results in the PR; local success is not a live plan.

After the human supplies read-only IAM, verify identity again and abort on any
account mismatch. Keep raw plan/output private, umask 077:

```bash
export AGENT_MODE=1 AWS_PROFILE=strall-dev-plan AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=623155450153 EXPECTED_ENVIRONMENT=dev
export EXPECTED_BINDING=strall-com-dev IAC_PREFIX=/iac
aws sts get-caller-identity --profile strall-dev-plan --region us-east-1 --no-cli-pager
# Confirm account exactly 623155450153 and the dedicated read-only role.
bash scripts/preflight.sh
bash scripts/plan.sh s3-bucket iot-digital-twin-artifacts \
  --plan-config examples/iot-artifact-bucket.strall-dev.json
```

Inspect the exact cache plan privately with terraform show -json. Use
scripts/evidence.py with a real, non-synthetic context and saved-plan digest;
never commit plan values or evidence. Stop on unexpected actions/resources,
missing backend or global bucket-name collision. No bootstrap is allowed.
The private live plan and evidence are available locally after restricted-role
preflight/planning. No raw evidence or plan values belong in Git or the PR.
Human review and separate approval remain required; no apply is authorized.

## Recovery and postflight

No resources or objects are changed by this task, so rollback is Git-only.
Later teardown or object/version deletion needs separate persistent-data review.
After a separately approved apply, read-only checks must confirm owner/account,
region, versioning, AES256, four public-access controls, ownership, tags and
absence of website/policy/lifecycle settings. Use scripts/postflight.py for the
reviewed runtime SSM expectation; native S3 reads cover bucket settings.
Versioning is retention protection, not independently verified backup/restore.
No postflight or operational observation is claimed before deployment.

## Local results (2026-10-09)

Terraform 1.15.2, Terragrunt 0.83.2, AWS provider 6.68.0.
make verify and make test pass with AWS_CONFIG_DIR=../aws-config: 61 tests,
one existing skip. Ruff format/lint, recursive Terraform formatting, and diff
whitespace checks pass. Backend-disabled module initialization/validation pass.
Two mock-provider Terraform plan tests pass. Initial checks without the explicit
config checkout and without sandbox registry/provider IPC access failed; corrected
invocations passed. No live plan, plan digest, or postflight evidence exists.

## Fresh verification after PR #12 merge

PR #11 was rebased onto main containing prerequisite merge
7b05c34f94fbb2d699ab2ec4dc73526d85f3a3ca. The fresh plan was generated from
rebased source 6395c0d4d91b0e076154869f6a33facafde890ab; the subsequent evidence-status edit changes documentation
only. Range-diff confirmed the two original PR #11 commits retained their changes.
No textual conflicts required resolution. The merged deployment/preflight path
retains Identity Center owner checks, S3 creation-plan-only config override,
agent-mode mutation blocking and separate normal human mutation approval.
AGENTS.md and the inherited bootstrap implementation remain unchanged.

Full deterministic verification passes: 85 Python tests with one existing skip,
backend-disabled S3 Terraform validation, two S3 mock-provider plan tests,
recursive formatting and diff whitespace checks. The restricted strall-dev-plan
identity, exact account, dev binding and expected backend were verified again.
The genuine fresh saved plan was privately inspected: exactly the six expected
creates, zero changes/deletes/replacements/drift, reviewed bucket/security controls,
no website/public policy/expiration configuration and no denied read.

New raw plan/JSON/context/evidence remain private and untracked. Earlier pre-rebase
plan evidence is historical and is not used as proof of the updated source.
No apply, config publication, IAM change or Lambda artifact upload is authorized
by the rebase or successful plan. Human review and separate execution approval
remain required; eventual published-config execution requires a new reviewed plan.
