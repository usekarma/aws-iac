# Lambda ownership and artifact handoff

aws-lambda owns runtime source, tests, reproducible ZIP packaging and artifact
version. aws-config owns desired function declarations and environment settings.
aws-iac owns Lambda resources, IAM, log groups, resource wiring, permissions,
triggers, runtime SSM metadata and deployment lifecycle. No Terraform is moved
into aws-lambda; this change does not modify that repository.

## Declaration v1

The consumer interface is [lambda-declaration-v1.schema.json](../contracts/lambda-declaration-v1.schema.json).
Use existing `functions` map keys as logical service names in the generic component;
IoT declares `ingest_function` and retains existing `ingest_lambda_name`.
Required per function: `runtime`, `handler`, `memory_size`, `timeout`,
`log_retention_days`, `artifact`. Optional `environment` maps non-secret workload
settings. Existing `src_type`/`src_nickname` and `vpc_nickname` discovery metadata
remain supported for generic functions; source fields must be paired.
IAM/policy/role/account/profile/command fields are not declaration inputs.

Artifact fields are `s3_bucket`, `s3_key`, `s3_object_version`, `source_code_hash`.
The key must identify a ZIP; `empty.zip`, absent versions, `null` and `latest`
versions are rejected. `source_code_hash` is base64 of the SHA-256 digest of the
raw ZIP bytes, not an S3 ETag. Terraform owns subsequent code updates; no
ignore_changes permits an external runtime deployer to bypass this ownership.

The [synthetic example](../examples/lambda-declaration.synthetic.json) is test
input only. Its bucket/version/hash/principal are invented fixture values and
must never be published or deployed. No actual artifact source is selected here.

## IoT binding

The first consumer requires basename `iot-digital-twin-ingest.zip`, runtime
`python3.12`, handler `app.lambda_handler`, and a nonempty
`environment.EXPECTED_PRINCIPAL` selected from an independently verified existing
identity association. The configured MQTT topic must equal
`devices/<device_id>/telemetry`, as required by the runtime. Log retention in the
function must match existing `cloudwatch_log_retention_days` while that legacy
field remains in the config contract.

IaC supplies `EXPECTED_DEVICE_ID`, `EXPECTED_PRINCIPAL`, `LATEST_STATE_TABLE`
and `MAX_CLOCK_SKEW_SECONDS`; derived wiring wins environment collisions.
Optional `ACCEL_MOTION_THRESHOLD_G`/`GYRO_MOTION_THRESHOLD_DPS` can use declaration
environment values. Other existing wiring is retained for compatibility.
The runtime's atomic conditional PutItem enforces increasing `sequence` and
writes `received_at`; no runtime algorithm changes occur here. Its watermark
must not expire while replay protection is required. The existing table TTL
attribute is not written by the current runtime; do not introduce expiration.
Offline scheduling, history and TwinMaker remain outside this change. No
certificates, policy attachments or secrets are created by this refactor.

## Publishing interface and required follow-up

No reviewed remote publishing mechanism exists in the inspected repositories.
An independently authorized release process must package/test the runtime in
aws-lambda, record source revision and ZIP digest, publish the unchanged ZIP to
an existing versioned S3 location, and return bucket/key/object VersionId/digest.
The package must contain app.py at ZIP root and dependencies required by the
runtime. The destination must be compatible with Lambda's region and explicit
artifact-read/KMS access. Publishing is a separate AWS mutation and is not
implemented or executed here. No bucket, publisher or upload/download hook added.

aws-config then records that immutable artifact reference and reviewed non-secret
settings; aws-iac reads the declaration via the existing SSM config path. A
reviewed saved plan and separate approval govern every actual code/resource update.
Reusing an S3 key is safe only with its exact VersionId. Digest metadata alone
does not attest provenance or compare remote object contents; release verification
must establish that reference/version/digest correspond to the tested bytes.

aws-config/main at 8637a8ae708dcc0bf9aec98db8bba45010e175e3 adopts
this interface under the coordinated contract v1. IoT uses an explicit draft:
`artifact: null`, with `planning_dependencies` containing `artifact_publication`
and `trusted_principal`. Structural validation accepts that declared blocked
state; it never supplies artifact coordinates or an expected principal. Resolved
artifact declarations still require all immutable reference fields. Generic
legacy declarations still require migration before planning.

Use `--require-resolved` for the separate pre-plan declaration gate: unresolved
IoT drafts fail. Terraform's artifact validation and explicit principal
precondition remain fail-closed; no resources are skipped to hide dependencies.

## Validation and migration

```bash
export AGENT_MODE=1 AWS_CONFIG_DIR=../aws-config
. .venv/bin/activate
make verify
make test
python scripts/check_config_contract.py --aws-config-dir ../aws-config
python scripts/check_lambda_declarations.py --aws-config-dir ../aws-config \
  --config-path iac/dev/iot-digital-twin/core2-aws-001/config.json
bash scripts/verify.sh --terraform iot-digital-twin
bash scripts/verify.sh --terraform lambda
```

The declaration check passes structural compatibility for the merged draft and
reports planning BLOCKED. Adding `--require-resolved` fails until actual artifact
and trusted principal inputs are supplied. Module tests use Terraform's mock provider and synthetic
bindings; `terraform test` in an initialized disposable copy of modules/lambda
requires provider downloads but makes no AWS calls. Tests prove declaration
mapping, trusted override behavior and artifact rejection, not live delivery.

Moved blocks relocate existing IoT Lambda/log group and generic Lambda instance
addresses without manual state manipulation. Names are preserved. Generic
runtime SSM paths stay unchanged; values now expose ARN/invoke ARN/artifact.
Existing out-of-band runtime/code writers must stop under a separately reviewed
handoff. New generic log groups may collide with pre-existing unmanaged groups;
inspect ownership and prepare an explicit reviewed import/migration proposal
before planning/execution. No import/state manipulation happens here.
Terragrunt copies the repository source root so shared-module relative paths work;
backend configuration, state keys and all mutation guards are unchanged.

Before a live plan: complete real artifact handoff,
principal binding, region/access/provenance, current state/resource/log ownership,
external writer handoff, owner/alerts/cost/recovery review and independently verified
account/profile/environment binding. Local/static validation is not deployment readiness.

## Coordinated validation

The source is aws-config/main 8637a8ae708dcc0bf9aec98db8bba45010e175e3,
contract v1. Tests compare both resolved/draft declaration schemas against the
explicit checkout and accept its IoT draft structurally, while strict readiness
rejects unresolved inputs. No AWS resources, live artifact access, deployment
or state migration are verified by local/static checks.
