# Final M1 additive discovery proposal (PR #22)

Target 623155450153, us-east-1. Operator reports one generated-role inline policy,
no boundary, no managed policies, no enabled Organizations SCPs, and assignments
to two accounts. These are operator attestations; the earlier reader could not
independently inspect role/boundary/SCPs. Earlier live permission-set reads matched
our baseline and confirmed no permission-set managed-policy attachments.

The smallest first-stage addition is discovery-policy.json: Cloud Control type/read
metadata, SiteWise model discovery/storage/encryption prerequisites, IoT ATS endpoint,
exact producer Thing/principals/policy, exact rule, exact routing-role reads, four
exact operational/ATOM config/runtime SSM reads, and exact legacy M1 stack reads.
Removed: historical/current state object reads, state version enumeration, logs,
quotas and unrelated Thing enumeration. Existing state/bucket/lock/config and owner
permissions are preserved byte-for-byte in the declaration structure.

The combined Terraform input is
examples/identity-center-owner.iac-plan-readonly.m1-discovery.json. It adds seven
non-conflicting statements to the existing declaration, changing no other fields,
assignments, tags, permissions, account restrictions or publisher configuration.
There are no new IAM mutation, PassRole, AssumeRole, Cloud Control write, ingestion,
certificate provisioning, MQTT or device rights. This is an Allow delta, not a
boundary; the operator attestations must cover the actual generated role.

## Explicit wildcard acceptance

Only APIs without resource-level IAM support use Resource *: Cloud Control
DescribeType/GetResource/ListResources, SiteWise ListAssetModels/storage/encryption
configuration, and IoT DescribeEndpoint. All new regional statements require
PrincipalAccount=623155450153 and RequestedRegion=us-east-1. IAM reads use exact
routing-role ARN and PrincipalAccount (IAM is global).

Cloud Control has no M1 type/name IAM fence for these actions. Combined downstream
reads may expose non-M1 resource properties; command filters are not security.
Approve this account/region-wide Cloud Control read exposure explicitly, or omit
those three actions and obtain operator-provided ownership/schema evidence. Do not
claim the combined role is M1-only: existing broad SSM parameter metadata, bucket
listing and owner permission-set metadata remain as before. No new historical-state
or unrelated resource-content reads are requested.

The same permission set is assigned to 835990279085. Every NEW statement has a
623155450153 PrincipalAccount guard, so it grants nothing to the second identity.
AWS Terraform provider updating the inline-policy resource automatically provisions
the permission set to ALL assigned accounts. A one-resource plan is not a one-account
operational change. Future human approval must cover both provisioning targets;
there is no provisioning authorized now. Existing assignments must remain no-op.
See [provider contract](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ssoadmin_permission_set_inline_policy).

## Bounded second-stage reads

This policy deliberately does not guess SiteWise UUIDs, Cloud Control service role,
producer certificate, or actual ATOM Thing/policy names. Obtain verified identities
then review exact-ARN additions: DescribeAssetModel/ListAssetModelProperties and
model-scoped ListAssets; DescribeAsset/DescribeAssetProperty/ListAssetProperties;
DescribeTimeSeries on the verified asset/time-series scope; exact certificate
DescribeCertificate/ListPrincipalThings; exact service-role/managed-policy reads;
and exact ATOM attachment reads. ListAttachedPolicies requires Resource *: prefer
operator-provided attachment evidence. No resource/* fallback. Cloud Control read
handlers may require additional downstream reads; a denial is unknown, not absence.
Preserve ATOM state, identity and attachments and shared resource ownership.

## Existing-owner maintenance / non-destructive plan

Authoritative owner:
/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8,
local state lineage adda9261-8df8-2be4-51cf-f829529878b3. Current locally inspected
state serial is 15, seven managed resources. Do not reuse earlier serial-13 scripts,
older single-ARN maintenance plans, or initialize a new owner/backend. Do not copy
state into an apply-capable competing workspace or use import/state manipulation.

1. Verify existing identity-center-plan STS account 835990279085. Re-read the live
   inline policy/attachments/assignments and obtain current operator attestations.
   Compare CURRENT state inline policy with the baseline, state hash/serial, current
   provider lock, source provenance and retained publisher overlay. Stop on drift.
2. Prepare a private maintenance review in the existing owner's maintenance-reviews.
   Retain all seven resources, including publisher Terraform source omitted from
   the original bootstrap-only source directory. Use the same-owner publisher
   provenance checks, adapted to CURRENT applied state, not old pinned scripts.
   New script review_m1_discovery_plan.py is an OFFLINE semantic gate, not a complete
   source-provenance verifier, planner, seal or apply authorization.
3. Build maintenance.tfvars.json from the owner's bootstrap.tfvars.json, changing
   ONLY bootstrap_config_json to the combined declaration. Preserve every other
   variable. Keep old declaration for rollback. Operator must provide enough
   authorized read access to refresh all seven existing resources; no admin fallback.
4. With complete reviewed source/overlay and original owner/backend intact, the
   planning commands are (operator preparation only; never apply):

```bash
export AGENT_MODE=1 AWS_PROFILE=identity-center-plan AWS_REGION=us-east-1
aws sts get-caller-identity  # require owner 835990279085 and existing reader
# OWNER=/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8
# REVIEW is a new private maintenance-reviews directory, never an old saved plan.
terraform -chdir="$OWNER" plan -input=false -lock=false -no-color -var-file="$REVIEW/maintenance.tfvars.json" -out="$REVIEW/review.tfplan"
terraform -chdir="$OWNER" show -json "$REVIEW/review.tfplan" > "$REVIEW/plan.json"
python3 scripts/review_m1_discovery_plan.py --owner-state "$OWNER/terraform.tfstate" --plan-json "$REVIEW/plan.json"
```

Do not run step 4 without step 2's publisher source: omission would plan deletions.
Never use refresh=false, -target or ignore_changes to conceal drift. Record original
owner files/state/lock hashes before and after and require unchanged results. Plan
must contain exactly one known inline-policy in-place update and six no-ops, no
moves/imports/replacements/drift, with identical before/after non-policy attributes.
Review full combined policy, archive source/provider/previous-state provenance,
hashes and both-account provisioning impact before a separate human approval.

No real saved plan was produced in this task: current reader lacks the full live
ownership/refresh evidence and the prior sealed helper pins stale state. This PR
supplies the declaration and offline plan gate; it is not a sealed apply bundle.
Preparing that bundle requires the current-owner provenance/refresh checks above.
No IAM mutation or permission-set provisioning is performed by either new file.

## Rollback and post-change verification (future approval only)

Rollback: retain old combined declaration and existing owner. Prepare a fresh
same-owner reverse plan that removes only the seven additions. Require human
approval of its saved-plan hash and both-account automatic provisioning. Never
restore old Terraform state or delete existing permissions/assignments. Partial
provisioning failure is a stop requiring authorized operator reconciliation.

After a separately approved future apply, verify actual role inline policy and
absence of attachments/boundaries using operator evidence; compare permission set,
assignments, publisher and second-account role. Refresh normal SSO session, then
run strall-dev-plan with explicit us-east-1:

```bash
aws sts get-caller-identity --profile strall-dev-plan --region us-east-1
aws cloudformation describe-type --profile strall-dev-plan --region us-east-1 --type RESOURCE --type-name AWS::IoTSiteWise::AssetModel
aws cloudcontrol list-resources --profile strall-dev-plan --region us-east-1 --type-name AWS::IoTSiteWise::AssetModel
aws cloudcontrol get-resource --profile strall-dev-plan --region us-east-1 --type-name AWS::IoT::TopicRule --identifier iot_digital_twin_operational_m1
aws iotsitewise list-asset-models --profile strall-dev-plan --region us-east-1
aws iot describe-endpoint --profile strall-dev-plan --region us-east-1 --endpoint-type iot:Data-ATS
aws iot get-topic-rule --profile strall-dev-plan --region us-east-1 --rule-name iot_digital_twin_operational_m1
aws iam get-role --profile strall-dev-plan --region us-east-1 --role-name iot-digital-twin-operational-m1-routing
aws ssm get-parameter --profile strall-dev-plan --region us-east-1 --name /iac/iot-digital-twin/operational-demo/config --query 'Parameter.{Name:Name,Type:Type,Version:Version}'
```

No role-arn/PassRole, decryption, writes or MQTT. Keep raw properties/config private.
Check every granted exact producer/config/runtime/legacy read; paginate inventories.
New read permissions should be absent in the second account and wrong-region
simulations. Negative IAM simulations must cover deployment, IAM writes/PassRole,
SSM writes, certificate provisioning, MQTT Connect/Publish and SiteWise ingestion
on exact resource ARNs, with real context and actual generated-role ARN. Never
invoke forbidden operations to test denial. Validate unchanged ATOM baseline.

## Acceptance and evidence

M1-IAM-01: exact additive declaration and account guards. M1-IAM-02: no removed
baseline rights or new mutations. M1-IAM-03: real plan permits one update/six no-ops.
M1-IAM-04: wrong-account/region new grants absent; ATOM/publisher unchanged.
Offline tests cover declaration invariants and synthetic allowed/rejected plans;
real plan and post-change cases remain unexecuted pending authorized evidence.
AWS service reference snapshot/URLs are in authorization-reference.json.
