# M1 read-only discovery proposal — not approved or applied

Target: existing `strall-dev-plan` / Identity Center `IaCPlanReadOnly`, account
623155450153, us-east-1, dev. Baseline: private
`iot-digital-twin/artifacts/m1-operator-readiness/awscc-readiness-report.md`,
aws-iac main f9a5c7d245311805f8b17c76ed9d1b66ea0ec577.
The stakeholder needs resource ownership evidence before planning the first 20
synthetic observations. Denied reads are unknown, never evidence of absence.

`discovery-policy.json` is an **additive proposal**, not active Terraform, an
attachment, or a complete replacement permission set. It preserves existing
permissions and all ATOM resources. An authorized owner must review the effective
permission set, boundaries and SCPs before approving a security change. Do not edit
the AWSReservedSSO role directly. Maintain its existing Identity Center owner;
re-provisioning the shared permission set needs separate human approval. Every
statement conditions PrincipalAccount because this permission set is also assigned
outside the target account. Regional services are restricted to us-east-1; IAM
uses its global endpoint and exact account-qualified role ARN.

## Stage 1: known names and metadata

| Evidence / observed missing read | Proposed scope |
| --- | --- |
| Cloud Control GetResource/ListResources; DescribeType | Account + region, Resource * (these actions do not support resource-level IAM). No role-arn or PassRole. |
| SiteWise ListAssetModels, DescribeStorageConfiguration, DescribeDefaultEncryptionConfiguration | Account + region, Resource *; required to discover UUIDs and operational prerequisites. |
| IoT DescribeEndpoint/ListThings | Account + region, Resource *; endpoint and Thing metadata discovery, not connections. |
| IoT DescribeThing/ListThingPrincipals/GetPolicy/GetTopicRule | Exact producer Thing, publish policy and M1 rule. GetPolicyVersion added to inspect declared versions. |
| IAM GetRole/ListRolePolicies/ListAttachedRolePolicies | Exact routing role; GetRolePolicy added to inspect inline restrictions. |
| SSM GetParameter | Four exact config/runtime names for operational-demo and ATOM preservation. No path enumeration or decryption permission. |
| Terraform S3 ListBucketVersions | Exact operational and ATOM state prefixes in the verified bucket; version history ownership. |
| Terraform S3 GetObject/GetObjectVersion | Two exact state keys, including historical versions; added prerequisite, not a recorded denied read. State can contain secrets: private handling only. |
| Legacy DescribeStacks/ListStackResources/GetTemplate | Only the named M1 legacy stack ARN with AWS-generated suffix. No stack deployment. |
| Logs DescribeLogGroups; ServiceQuotas ListServiceQuotas | Account + region, Resource *: metadata prerequisites, no log event reads. These APIs cannot IAM-enforce a log prefix or CLI service-code filter. Omit if operator inventory supplies this evidence. |

Wildcard security review: metadata calls can disclose unrelated resource names,
quotas, logging metadata and schema. Cloud Control cannot enforce M1 type/name
filters in this policy; CLI filters are not authorization. Existing downstream
permissions may make other resource properties readable through Cloud Control.
Review the **combined** role privileges, not just this delta. If this exposure is
unacceptable, omit Cloud Control calls and obtain an operator-supplied inventory.
Do not add unsupported cloudformation:TypeName or identifier conditions. Scoped
CloudFormation stack reads support ARN restrictions; DescribeType does not.

## Stage 2: bind discovered IDs, do not widen to account-wide describes

Stage 1 intentionally does not resolve every recorded denial. Add a separately
reviewed exact-ARN supplement only after identity/ownership is established:

| Still missing / additional prerequisite | Exact binding needed |
| --- | --- |
| Recorded iotsitewise:ListAssets | M1 asset-model ARN (the action supports asset-model scope). A top-level list without model ID is not authorized; supply model UUID. |
| DescribeAssetModel/ListAssetModelProperties | Same verified model ARN. Confirm measurement name/type, not only its display name. |
| DescribeAsset/DescribeAssetProperty/ListAssetProperties/ListAssociatedAssets | Verified asset ARN; verify model link and INTEGER Severity measurement. |
| Recorded DescribeTimeSeries | Verified asset/time-series ARN as required by alias lookup; reconcile alias `/adage/iot-digital-twin/operational-demo/asset-000/severity`. Do not invent an alias IAM condition. |
| iot:DescribeCertificate/ListPrincipalThings | Exact dedicated producer certificate ARN; no certificate listing or provisioning. |
| iot:ListAttachedPolicies | Resource * required by AWS; separately account/region-guarded. This discloses attachment metadata more broadly; use operator evidence if unacceptable. |
| IAM GetRole/GetRolePolicy/ListRolePolicies/ListAttachedRolePolicies | Exact verified Cloud Control service-role ARN; it is currently unknown. Inspect trust and downstream handler permissions without assuming it. |
| IAM GetPolicy/GetPolicyVersion | Exact discovered managed policy ARNs; no policy/* or role/* fallback. |
| IoT DescribeThing/ListThingPrincipals/GetPolicy/GetPolicyVersion | Actual verified ATOM Thing/policy ARNs; repository nickname atom-lite-001 is not proof of an AWS Thing name. Certificate reads as above if needed. |

New SiteWise/IAM/certificate reads above are inferred prerequisites, not previously
observed denials. Retain PrincipalAccount and RequestedRegion guards on regional
supplements; account guard on IAM. Cloud Control model/asset read handlers may
need additional downstream reads (e.g. composite models or tags); authorize only
confirmed read actions on the discovered IDs after inspecting DescribeType schema
or a precise denial. This staged policy is deliberately not deployment-ready.

## Approval boundaries and preservation

Not granted: Cloud Control Create/Update/Delete, Terraform lock writes, import or
state modification, IAM mutation/PassRole/AssumeRole, SSM publication, KMS Decrypt,
certificate/key provisioning/activation/attachment, IoT Connect/Publish/Subscribe/
Receive, SiteWise ingestion, MQTT or device operations. Existing effective role
permissions must also be reviewed: this delta is not a deny boundary.
Deployment caller permissions, Cloud Control service-role trust/handler privileges,
IoT routing alias/source fences and a dedicated MQTT producer identity are separate
approvals. Never reuse ATOM credentials. Compare private ATOM state, Thing,
certificate/policy attachments and shared resource owners before any future plan;
unknown ownership blocks deployment. No state migration is authorized.

## Non-mutating operator verification

Only after an authorized owner approves and applies an exact reviewed policy:

```bash
export AWS_PROFILE=strall-dev-plan AWS_REGION=us-east-1 AWS_PAGER=''
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}'
# Stop unless account is 623155450153 and role is the existing IaCPlanReadOnly.
aws cloudformation describe-type --type RESOURCE --type-name AWS::IoTSiteWise::AssetModel
aws cloudcontrol list-resources --type-name AWS::IoTSiteWise::AssetModel
aws cloudcontrol get-resource --type-name AWS::IoT::TopicRule --identifier iot_digital_twin_operational_m1
aws iotsitewise list-asset-models --query 'assetModelSummaries[].{id:id,name:name}'
aws iot describe-thing --thing-name adage-operational-m1
aws iot list-thing-principals --thing-name adage-operational-m1
aws iot get-policy --policy-name iot-digital-twin-operational-m1-publish
aws iot get-topic-rule --rule-name iot_digital_twin_operational_m1
aws iam get-role --role-name iot-digital-twin-operational-m1-routing
aws iam list-role-policies --role-name iot-digital-twin-operational-m1-routing
aws iam list-attached-role-policies --role-name iot-digital-twin-operational-m1-routing
aws ssm get-parameter --name /iac/iot-digital-twin/operational-demo/config --query 'Parameter.{Name:Name,Type:Type,Version:Version}'
aws s3api list-object-versions --bucket 623155450153-tf-state --expected-bucket-owner 623155450153 --prefix iot-digital-twin/operational-demo/terraform.tfstate
```

Use an explicit region on each call if not using the exported region. Keep raw
resource properties, policy documents, SSM values and state private, untracked,
mode 0600. No GetParameter --with-decryption. Verify config/runtime locally without
printing their values. Paginate inventories; an empty successful response proves
only that request's scope. AccessDenied remains unknown. Re-run the existing
operator-inventory.sh only with verified service-role/certificate/ATOM bindings;
its unsupported top-level ListAssets/alias requests may still be denied until the
exact-ID supplement and model-qualified request are used. No escalation fallback.

Expected evidence: exact identity, successful metadata calls, IDs and owners,
state version reconciliation, trusted service role, dedicated ACTIVE producer
certificate and attachments, unchanged ATOM baseline. This is discovery, not a
Terraform plan or authorization to deploy. No live verification of proposed grants
is possible before approval; offline checks do not establish effective IAM access.

## Local verification and authoritative references

The regression tests check exact action allowlists, AWS read annotations, resource
support for wildcard statements, account/region guards, state prefixes and absence
of mutations. The reference fixture is a selected snapshot of AWS's public service
reference JSON; source URL/version accompany each service. It is not an IAM policy
simulator and cannot model SCPs, boundaries, denies or Cloud Control handler calls.
See [AWS service reference](https://docs.aws.amazon.com/service-authorization/latest/reference/service-reference.html)
and the per-service URLs in authorization-reference.json. No IAM or AWS resource
changes are needed to run repository verification.
