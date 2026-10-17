# M1 AWSCC evaluation and proposed first-deployment implementation

Decision: suitable for the first M1 deployment, conditional on inventory and human
review. Replace one opaque Terraform CloudFormation stack with three AWSCC resources:
model, asset/property binding and native IoT rule. No service behavior, IAM policy,
producer identity, ATOM resource, config schema or state operation is changed here.
Reviewed aws-iac main fc3cbfb and aws-config main dc68c3b. Existing deployed-resource
ownership remains unverified; earlier denied reads are NOT evidence of absence.

## Exact support independently checked

Downloaded signed hashicorp/awscc 1.106.0 and inspected terraform providers schema
-json, not merely generated documentation examples. Validated the actual configuration
with Terraform 1.15.2, existing AWS provider 6.69.1 and AWSCC 1.106.0. Lock records signed
release checksums; AWS provider version/hashes retained. No new Python dependency.

| M1 requirement | AWSCC declaration/output |
| --- | --- |
| Model | awscc_iotsitewise_asset_model.model, same model name |
| Measurement | asset_model_properties: name severity, INTEGER, logical_id Severity, type_name Measurement |
| Asset | awscc_iotsitewise_asset.asset, asset_model_id from model.asset_model_id |
| Binding/alias | asset_properties logical_id Severity, exact existing severity alias, notification_state DISABLED |
| Native routing | awscc_iot_topic_rule.telemetry, same rule name, SQL, IoT SiteWise action and GOOD integer timestamp/value templates |
| Runtime | same model_id/asset_id/account/region/alias/topic/client ID fields; direct resource IDs rather than stack outputs |

AWSCC exposes no separate property resource: model measurement and asset alias are
nested attributes. The pinned CloudFormation schema marks generated property IDs
read-only; do not provide fake UUIDs. Logical ID supplies the binding. Independent
schema inspection confirms import identifiers are model UUID, asset UUID and rule name.
The pinned source marks AssetModelType create-only and RuleName create-only; property
changes still require data-loss review even when Terraform reports an in-place update.

## Lifecycle and ownership comparison

| Concern | Current stack | Proposed AWSCC |
| --- | --- | --- |
| Terraform ownership | One stack state entry; stack owns model/asset/rule | Three resource entries in the same operational-demo state; no stack |
| Dependencies | CloudFormation Ref/GetAtt and DependsOn | Explicit model -> asset -> rule Terraform graph; rule also waits for routing policy |
| Failure | Stack attempts configured/default rollback across its resources; not an atomic data transaction | Independent Cloud Control operations; partial completion and no automatic rollback |
| Drift | Terraform primarily sees template/stack; nested service drift needs separate inspection | Per-resource Cloud Control reads/plans; optional/computed defaults still limit drift detection |
| Update/delete | Stack handlers coordinate nested resources | Same CloudFormation type handlers through Cloud Control, individual create/update/delete requests |
| Configuration | Explicit CloudFormation execution role binding | Preserve that binding as AWSCC role_arn (Cloud Control service role), not Terraform assume_role |
| Dependencies | AWS provider plus stack template | AWS provider plus exact-pinned AWSCC; more granular state, no hand-built stack template |

This removes stack/template/output glue; it does not eliminate CloudFormation handlers,
service IAM, asynchronous stabilization or operational recovery. AWSCC resources expose
no Terraform timeouts block in this pin; unlike the previous stack's explicit 15-minute
limit, use provider/Cloud Control request status and reviewed operator execution-window
limits. Do not assume a shell timeout rolls back or cancels an in-flight operation.
On partial failure stop, reconcile actual IDs/state/request status, then review recovery.

Provider documentation warns about optional/computed defaults: explicitly configure
measurement type, logical IDs, alias, notification state, rule-enabled state, SQL
version and TQV fields. Live convergence/drift and regional handler availability are
not established by offline tests; smoke evidence is required after approved deployment.

## IAM and aws-config compatibility

Root awscc provider uses the same explicit region and existing cloudformation_role_arn
as role_arn. It does not use assume_role and does not fall back to caller-based execution
as an intended deployment mode; current readiness and model preconditions still reject
null role/principal/region, wrong account and unresolved planning dependencies.
AWSCC service role is assumed by cloudformation.amazonaws.com via Cloud Control.
The existing field/dependency name therefore remains semantically valid; no aws-config
schema or declaration change is needed. Do not remove the execution-role readiness gate.

Caller needs Cloud Control permissions in the cloudformation namespace, such as
CreateResource/GetResource/GetResourceRequestStatus/UpdateResource/DeleteResource and
CancelResourceRequest if recovery uses cancellation, plus scoped iam:PassRole for the
explicit service role. Review resource-type restrictions, boundaries and SCPs. Exact
needed permission scope is a separate IAM review, not granted by this implementation.
The service role still needs downstream handler rights. The pinned schemas include:
- Model: describe/create/update/delete/tag, list model properties/composites; some
  handlers also support composite/interface operations. Review actual called paths
  rather than granting all schema permissions indiscriminately.
- Asset: describe/create/update/delete/tag, list asset/model properties and associations,
  UpdateAssetProperty for alias configuration; hierarchy rights only if actually needed.
- Rule: create/get/replace/delete/tag/list-tags and exact routing-role iam:PassRole.

Routing execution policy/trust, producer MQTT policy, role name, log group/retention,
fixed principal predicate, time-series alias fence and ATOM separation are unchanged.
No AWS role or permission was created/modified. Read-only plan/refresh may additionally
require Cloud Control GetResource and downstream handler reads under the service role;
the earlier IaCPlanReadOnly role's denied inventory remains a release blocker.

## Deployment and migration stop conditions

For a truly fresh state/resource set: review a plan creating these three AWSCC resources
plus the same separately owned producer/routing/log/runtime objects. Preserve shared
bucket/backend/Identity Center and all ATOM identities/resources. No state bootstrap.

If aws_cloudformation_stack.sitewise exists in state, this code removes that declaration:
an ordinary plan can schedule stack deletion, including model/asset/history/rule.
DO NOT APPLY that plan. No moved/removed/import blocks or state manipulation are supplied.
A stack cannot be moved into three AWSCC resources with a simple moved block.

Before migration: authorized inventory and backups/history export; review retaining
nested resources and safely detaching them from stack ownership; separately review
imports using discovered model ID/asset ID/rule name; reconcile state and demonstrate
no-op AWSCC plan before any release. Never let both owners manage the same objects.
If unmanaged resources exist, reconcile/import under separate approval; do not attempt
new resources with the same aliases/names and interpret failures as cleanup permission.
If stack retention/import cannot be made safe, keep main's current design.

## Verification

Component provider mocks test exact INTEGER measurement, model/asset ID link, logical
binding, alias and disabled notifications, unchanged routing/TQV and alias-scoped IAM.
Existing durable reset/session-fencing mock test still passes. A standalone module plan
mock expects rejection for wrong region (root tests cannot target a child's check object).
No mock calls real AWS. Complete repository gates and backend-disabled init/validate
are required, with negative module test included in CI. Semantic comparisons confirm
all existing AWS producer/IAM/log declarations and locals unchanged.
No deployment, import, IAM/credential change, device operation or live MQTT performed.

## Primary sources

- [Pinned model resource](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/docs/resources/iotsitewise_asset_model.md)
- [Pinned asset resource](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/docs/resources/iotsitewise_asset.md)
- [Pinned provider authentication/defaults](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/docs/index.md)
- [Pinned model handler schema](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/internal/service/cloudformation/schemas/AWS_IoTSiteWise_AssetModel.json)
- [Pinned asset handler schema](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/internal/service/cloudformation/schemas/AWS_IoTSiteWise_Asset.json)
- [Pinned rule handler schema](https://github.com/hashicorp/terraform-provider-awscc/blob/v1.106.0/internal/service/cloudformation/schemas/AWS_IoT_TopicRule.json)
- [AWS Cloud Control operations and failure behavior](https://docs.aws.amazon.com/cloudcontrolapi/latest/userguide/resource-operations.html)
