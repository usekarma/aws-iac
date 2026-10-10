# Single exact IoT config read for IaCPlanReadOnly

Concern: planner IAM only. The separately reviewed aws-config rule-name correction
is independent; neither change resolves trusted_principal or authorizes config
publication, workload deployment, certificates, seal or IAM apply.

## Completed human maintenance

The human completed seal, independent manifest review, explicit mutation approval,
and exact saved-plan apply against the original retained state owner. The genuine
plan was **0 creates / 1 update / 0 deletes / 0 replacements**, with six no-op
resources. Only `aws_ssoadmin_permission_set_inline_policy.inline_policy` changed,
adding the single config ARN below to the existing `ssm:GetParameter` Allow.
No additional permission scope or action was added by this reconciliation.

Reviewed saved-plan SHA-256:
`d4ae8ae3ffe728f74a20a3d84a44fc18de18ba2d690bca81b33233aeba9ca839`.
Reviewed manifest SHA-256:
`07e3340f637d6cfe0e1c17db23e5cebf856ec46bdc40dae4cb49b9883fdcd0ab`.
The retained `apply-result.json` records Terraform return code **0** and that exact
manifest digest. The successful read-only `post-apply.json` records status
`verified`, unchanged 32-action set, conditions and assignments, no managed-policy
additions, and unchanged other permission sets.

The workload probe used `strall-dev-plan` in account `623155450153`, caller
`arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_IaCPlanReadOnly_92e4b2f1ca02a611/admin`.
Its exact observed outcome was **ParameterNotFound**, `authorized:true` and
`parameter_exists:false`. The config-read IAM blocker is closed as of that
postflight; the parameter **did not exist at the time of the probe**. This was not
a successful parameter retrieval, and SSM publication remains unproven. No fresh
AWS probe was performed during this documentation reconciliation.

The authoritative state retains lineage
`adda9261-8df8-2be4-51cf-f829529878b3`, advanced from baseline serial **13** to
postflight serial **15**, with postflight state SHA-256
`5b25cc02532bc9c1d42aa89ab7eff4f75d4689f6ea599bc933611fedd7780571`.
No second state owner, import or adoption was created.

Private execution evidence remains in
`/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/iot-config-read-6zmoojc2`:
`iot-config-read-manifest.json`, `review.tfplan`, `apply.log`, `apply-result.json`
and `post-apply.json`. The successful postflight receipt SHA-256 is
`0684e0195d32c49ee42e04752374d8c197610c6fe638957f41da734029a012fb`.
Only references and digests are recorded here; private receipts, saved plans,
state, and earlier failure/success evidence remain unmodified and uncommitted.

Postflight is **point-in-time** managed-state/inventory verification, not a global
audit. Its explicit scope is `IAM config-read maintenance only`, with
`config_publication_performed:false` and `ingestion_readiness:NOT_VERIFIED`.
`trusted_principal` remains unresolved and `EXPECTED_PRINCIPAL` remains absent.
Config publication, genuine ingestion planning, backend-read permission review if
needed, and workload execution remain separate concerns. No S3 permission was
broadened, no certificate/credential was created, and no workload was deployed by
this maintenance unit. Do not repeat the completed seal or apply.

Existing workload planning identity: strall-dev-plan, account `623155450153`,
IaCPlanReadOnly. Add **only** this resource to the existing `ssm:GetParameter`
ReadBindingAndRuntime Allow:
`arn:aws:ssm:us-east-1:623155450153:parameter/iac/iot-digital-twin/core2-aws-001/config`.
The new revision is
`examples/identity-center-owner.iac-plan-readonly.iot-config-read.json`.
It preserves every other statement, all 32 actions, existing exact region/account
scopes and owner-only Identity Center conditions, PS identity/PT1H/tags and both
existing USER assignments. No action, wildcard, SSM write, managed policy, S3 state
scope or other resource is added. The deployed publisher remains unchanged.

## Authoritative owner and restricted planning

Use only `/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8`.
Pre-apply baseline lineage `adda9261-8df8-2be4-51cf-f829529878b3`, serial **13**, state SHA-256
`221cd1cd4e517b46472888585ddfab1a28aa436cd7c9f07ea9ad4cf41d09906e`.
The original publisher manifest and successful read-only recheck are preserved.
State owns seven resources: two permission sets, two inline policies, and three
USER assignments. No second backend/state, import/adoption, move, init or state
repair is introduced. Historical executor/planner Python sources remain unchanged.

The additive plan-only command `scripts/plan_iot_config_read.py` loads the existing
authoritative repository's sealed maintenance integrity helpers. It does not alter
their human-only seal/apply/postflight guards or call their execution paths. It
requires explicit AGENT_MODE=1, identity-center-plan, account `835990279085`,
region us-east-1, rejects competing credentials/arguments, and verifies STS
AWSReservedSSO_IaCPlanReadOnly before Identity Center discovery. AdministratorAccess
and workload-account profiles are not permitted for this control-plane plan.

The verified publisher source snapshot is temporarily present in the original
initialized owner during plan, then removed; its exact bytes are retained in the
new private bundle and binary plan. Original source/backend/lock/variables, state
hash/lineage/serial, baseline declaration and historical recheck provenance must
match. No live metadata mutation or config publication is required for the plan.

Expected Terraform: **0 creates / 1 in-place update / 0 deletes**. Only
`aws_ssoadmin_permission_set_inline_policy.inline_policy` changes. The other six
resources must be no-op with exact before/after identity. Reject drift, unknown
policy values, imports, moves, extra resources, creates, replacements, deletes or
any policy delta beyond this one ARN. Binary source/lock/previous state/variables
must match the reviewed inputs. Private scripts/evidence.py summaries are generated
through the existing helper. Restricted planning remains separate from the HUMAN
executor described below; no execution is authorized by the plan command.

```bash
cd /home/ted/dev/aws-iac/artifacts/worktrees/iot-ingest-config-read
export AGENT_MODE=1 AWS_PROFILE=identity-center-plan AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=835990279085
umask 077
/home/ted/dev/aws-iac/.venv/bin/python scripts/plan_iot_config_read.py plan
```

## Readiness limits and human boundary

Rule-name schema readiness must pass for `core2_aws_001_ingest_rule`. All artifact
coordinates/size and trust fields remain unchanged. The explicit trusted_principal
dependency and absent EXPECTED_PRINCIPAL must continue to block publication and
strict ingestion planning. The historical IAM plan addressed the observed exact
config read denial. The completed execution above verifies the grant and the
parameter's absence at postflight; it does not establish config publication.

Do not claim this one resource grant is sufficient for every future workload read:
the current role's S3 GetObject scope is still the artifact-bucket component state,
not `iot-digital-twin/core2-aws-001/terraform.tfstate`. No expansion is made here.
Once principal/config prerequisites are resolved, review any legitimate backend/
refresh read denials minimally; never add speculative broader grants now.

Checks: exact delta/action-set/assignment/condition tests, rejects wrong identity/
mode/overrides, rejects any unexpected plan action, proves same-owner plan and
overlay cleanup without init/apply/state repair, full make verify/test and source
hash evidence. Genuine counts are reported only after an actual restricted plan.

The original plan/evidence boundary required separate human review, seal and
mutation approval for this IAM concern. Those steps are now completed through the
executor below. Never feed this plan into historical config-read/publisher/
owner-planning executors or rerun its apply. Further config/workload work requires
its own review and approval.

## Genuine restricted plan evidence

The genuine plan was generated with identity-center-plan in owner account
835990279085, caller
`arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b/admin`.
Result: **0 creates / 1 in-place update / 0 deletes**, six no-op resources. Only
aws_ssoadmin_permission_set_inline_policy.inline_policy changes. No replacement,
import, move or unexpected resource was accepted. At plan generation, state
remained serial 13 and the exact baseline SHA-256 above; the temporary source
overlay was removed. The completed apply later advanced serial to 15.

Private review:
`artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/iot-config-read-6zmoojc2`.
Saved plan SHA-256:
`d4ae8ae3ffe728f74a20a3d84a44fc18de18ba2d690bca81b33233aeba9ca839`.
Plan JSON SHA-256:
`1c11c211aeba2b9a4c9f53f503a9fdd1dfe786ea521865f2229d8d0aa7a9df06`.

An initial generator reference was incorrect after the live plan had already
passed every resource/provenance check. The evidence-only call was corrected to
the existing publisher evidence generator. No live plan was rerun, binary/JSON/
declaration/state was changed, or AWS call made during that repair. The exact
original planning script is retained privately as planning-script.py; owner.json
keeps its original source hash. evidence-repair.json records both original and
corrected code hashes and the repair scope. Human review must include that explicit
provenance record before seal/apply; no historical input was silently rewritten.
The human subsequently sealed and applied this exact bundle as recorded above.

## HUMAN-only exact saved-plan executor

`scripts/maintain_iot_config_read.py` supports only seal/apply/postflight for the
existing `iot-config-read-6zmoojc2` bundle. It reuses the existing owner maintenance
guard, requires explicit AGENT_MODE=0, HUMAN_MAINTENANCE_APPROVED=1,
identity-center-admin, owner 835990279085 and us-east-1, and rejects agents before
any tool execution. Apply additionally requires AWS_MUTATION_APPROVED=1 and an
independently supplied reviewed manifest SHA-256. No single acknowledgement
authorizes both entry and mutation; normal planning still uses restricted IAM.

Before sealing, the binary plan is re-exported with read-only terraform show and
must equal the existing reviewed JSON and digests above. Its source, provider
lock, previous managed state and variables must match the retained owner/review.
Only the exact one-ARN update and six no-ops are accepted. Metadata, assignments,
conditions, actions and all other resource scopes remain unchanged.

The explicit evidence-only repair is checked byte-for-byte: the retained original
script may differ from current planning code only by replacing execution.generate
with execution.publisher.generate. Both hashes and evidence-repair.json are bound
into the new manifest. Original owner.json keeps its original hash; no plan,
historical evidence, declaration or state is rewritten to mask the repair.
The manifest also binds original maintenance helper sources, exact owner/backend/
provider-lock/variables, current proposal/executor, all review files and previous
verified publisher records. Source/config/state drift after sealing fails closed.

### Historical human execution commands

The following documents the guarded execution interface used for the completed
operation. It is not an instruction to repeat seal or apply: the existing manifest
and recorded execution attempt deliberately block both. Before the original seal,
the human reviewed code, tests, policy delta, saved plan and evidence-repair record.

```bash
cd /home/ted/dev/aws-iac/artifacts/worktrees/iot-ingest-config-read
umask 077
export AGENT_MODE=0 HUMAN_MAINTENANCE_APPROVED=1
export AWS_PROFILE=identity-center-admin AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=835990279085
export OWNER_DIR=/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8
export REVIEW_DIR="$OWNER_DIR/maintenance-reviews/iot-config-read-6zmoojc2"

/home/ted/dev/aws-iac/.venv/bin/python scripts/maintain_iot_config_read.py seal identity-center-permission-set \
  --owner-dir "$OWNER_DIR" --review-dir "$REVIEW_DIR"
```

Seal performs read-only STS/Identity Center inventory, requires the existing
planning and publisher policies/assignments to match, and writes only the private
iot-config-read-manifest.json. It never overwrites/reseals a manifest. Independently
record/review the printed digest outside the bundle as REVIEWED_MANIFEST_SHA256.
Seal is not mutation approval. Only after separate explicit approval:

```bash
AWS_MUTATION_APPROVED=1 \
/home/ted/dev/aws-iac/.venv/bin/python scripts/maintain_iot_config_read.py apply identity-center-permission-set \
  --owner-dir "$OWNER_DIR" --review-dir "$REVIEW_DIR" \
  --manifest-sha256 "$REVIEWED_MANIFEST_SHA256"
```

Apply rechecks every hash, owner serial/state, exact plan/delta and live inventory,
then invokes only `terraform apply -input=false -no-color /EXACT/review.tfplan` in
the existing owner. No init, replan, saved-plan replacement, source restoration,
import/adoption, new backend/state or alternate mutation path is present. Any
execution attempt blocks re-execution; failures retain state/logs for human
investigation with no automatic retry, rollback or permission expansion.

Successful apply runs read-only postflight automatically. A human may rerun only
postflight after a recorded successful apply:

```bash
/home/ted/dev/aws-iac/.venv/bin/python scripts/maintain_iot_config_read.py postflight identity-center-permission-set \
  --owner-dir "$OWNER_DIR" --review-dir "$REVIEW_DIR" \
  --manifest-sha256 "$REVIEWED_MANIFEST_SHA256"
```

Postflight requires the original state lineage with an advanced serial, exactly
seven managed resources, unchanged six no-ops, and only the exact policy delta.
The same permission-set ARN/PT1H/tags, all assignments, managed-policy attachments,
publisher and unrelated discovered permission sets must match the sealed inventory,
with only the new inline-policy resource grant differing. This is point-in-time
inventory/state evidence, not a CloudTrail audit of every external operation.

The config-read probe uses **strall-dev-plan** after verifying account 623155450153
and AWSReservedSSO_IaCPlanReadOnly. It reads only the exact config path's version,
never its value and never writes SSM. ParameterNotFound is acceptable IAM
authorization evidence and records parameter_exists:false; AccessDenied or another
failure stops postflight without broadening. Successful publication is not implied.
No S3 state permission, rule-name change, principal resolution, certificate,
config publication or workload deployment follows this path. Stop after postflight.

## Adversarial executor review

Review tightened three behaviors without changing the historical saved plan or
IAM declaration. First, all resources, including the allowed caller-identity data
source, explicitly reject move/import/replacement markers and unknown actions.
The allowed data source must retain its exact AWS type/provider. The existing pinned
binary and JSON remain mandatory; this closes a fail-closed validation gap rather
than permitting a new plan.

Second, a repeated successful read-only postflight no longer overwrites its original
failure/success record. The primary post-apply.json is created exclusively; later
receipts go to private postflight-rechecks/review-*/postflight.json with the previous
record hash. Apply failure recording follows the same evidence-preserving rule.
These are local evidence writes, never permission to rerun mutation.

Third, ParameterNotFound is accepted only as a single well-formed GetParameter
service-error line with AWS CLI v2 return code 254, no stdout and no AccessDenied.
Timeouts, missing/expired credentials, mixed diagnostics, malformed success/version
output and unexpected return codes fail. See
[AWS CLI return codes](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-returncodes.html).
The resulting receipt explicitly limits verification_scope to IAM config-read
maintenance, records config_publication_performed:false and
ingestion_readiness:NOT_VERIFIED. Even an existing parameter response verifies
permission/existence/version only, not its desired content or deployment readiness.

The pre-execution review used synthetic negative tests and read-only genuine-bundle
integrity validation; it performed no seal/apply or AWS mutation. The human's later
seal/apply/postflight is recorded in the completion section. This reconciliation
likewise performs only deterministic tests and local read-only integrity checks,
preserving the implementation, sealed inputs and all historical receipts.

## Completion reconciliation validation

All 18 targeted maintenance tests and nine proposal/regression tests passed.
`make verify` and `make test` each ran 154 tests successfully with one expected
config-publisher-only skip. This linked worktree requires the repository's
explicit local dependency setting `AWS_CONFIG_DIR=/home/ted/dev/aws-config`;
the initial runs without it failed two existing cross-repository contract checks
because the CI-style nested `aws-config/` checkout was absent. No gate or test
was weakened to resolve that setup failure.

Ruff lint/format checks for all four new Python files, recursive Terraform
formatting, and staged whitespace/diff checks passed. Local read-only integrity
validation checked the independent manifest digest, source/declaration/history
hashes, retained backend/provider lock/variables, saved binary-to-JSON equality,
exact one-update plan and six no-ops, current state lineage/serial/hash, and
successful execution receipt. Terraform show required permission to start its
local provider plugin outside the sandbox; it made no AWS call. Human-only
seal/apply/postflight entrypoints were not invoked by the reconciliation.

The six durable files are the reviewed IAM declaration (specification input),
restricted planner and human executor (implementation), this specification with
execution references, and two deterministic test files. No raw evidence or
generated artifacts are included. Implementation and declaration bytes remain
identical to the human-sealed inputs; only this specification was updated during
completion reconciliation.
