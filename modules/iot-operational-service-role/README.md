# M1 Cloud Control service-role proposal — not wired/deployed

Owner: aws-iac canonical iot-digital-twin component, operational-demo state.
Explicit deployment_stage selects IAM-only bootstrap then operational deployment.
The role module remains at module.cloud_control[0] in BOTH stages; no competing
backend/state owner. See docs/m1-two-stage-bootstrap.md. No role is deployed yet.
Configurations without deployment_stage retain their existing external-role behavior.

Existing reuse: operator reports empty IAM search for cloudformation.amazonaws.com
trust in 623155450153. Reader STS is verified; ListRoles denied. Record this as
operator-reported lack of a candidate, not agent-proven absence of every IAM role.
Exact proposed-name collision/owner must be checked by authorized operator before
wiring or creation. cloudformation_role_arn therefore remains UNBOUND.

## Exact trust and authority split

Role name proposal: iot-digital-twin-operational-m1-cloud-control. Trust contains
ONLY cloudformation.amazonaws.com -> sts:AssumeRole, as documented for Cloud Control;
no human, account root, IoT service or resources.cloudformation.amazonaws.com trust.
Do not copy registry/StackSet SourceArn conditions: no documented concrete Cloud
Control SourceArn/account context was established for this RoleArn path. Adding
untested context keys can block all requests; IfExists is not an enforced fence.
Acceptance must explicitly review service-principal-only trust, paired with
same-account exact caller PassRole and constrained downstream permissions.

The CALLER separately needs cloudformation CreateResource/UpdateResource/DeleteResource,
GetResource/GetResourceRequestStatus and required read/type actions. Those resource
operation APIs require Resource *; restrict caller account/region and review blast
radius. Caller iam:PassRole must target only this VERIFIED role with
PassedToService=cloudformation.amazonaws.com. No caller policy is changed here.
The service role does NOT need Cloud Control or IAM role-creation permissions.

The SERVICE role has only SiteWise handler operations and exact IoT rule CRUD/tag/read.
Its own iam:PassRole permits only iot-digital-twin-operational-m1-routing, with
PassedToService=iot.amazonaws.com. Routing role remains separate: IoT runtime trust,
alias-fenced BatchPutAssetPropertyValue and error-log writes. Service role has no
MQTT publish, telemetry ingestion, certificates, producer/ATOM policies, SSM or
CloudWatch runtime rights, and creates no routing role itself.

## Least privilege / handler compatibility limits

CreateAssetModel requires Resource *: mandatory Project=iot-digital-twin,
Experiment=operational-telemetry and Environment=sandbox request tags, plus exact
account/us-east-1. CreateAsset uses owned model ARN namespace and same request tags.
Existing model/asset lifecycle reads/updates/deletes require all three resource tags
in target account/region. UUIDs do not exist yet, so their ARN suffix is wildcard;
tags are an ownership fence, NOT proof of unique M1 names. Another asset with matching
tags could be managed. Consider narrowing UUIDs after confirmed provisioning in a
separate reviewed update. Never tag existing unrelated objects to bypass ownership.

Ownership tag changes/removal are blocked: TagResource preserves matching values,
UntagResource omitted. Exact IoT rule ARN eliminates unrelated rule changes. Its
limited tag rights apply only to that rule. UpdateAssetProperty is asset/tag-scoped;
IAM does not establish an exact alias fence for that configuration API. Reviewed
Terraform provides the one desired alias; no claim that role alone enforces it.

Pinned AWSCC 1.106.0 handler schema lists additional hierarchy/composite/interface
MUTATION APIs. These are omitted because M1 has one flat measurement and no hierarchy.
Required composite/interface metadata reads are included. Fixed tags avoid tag-removal
updates; rule UntagResource omitted. This is a least-privilege candidate, NOT a claim
that every AWS handler path is verified. Creation MUST forward tags in the initial
API request; if a handler tags only afterwards, mandatory request-tag conditions
will intentionally deny creation. Do not drop fences to obtain a successful deploy;
review the exact handler request/denial and adjust implementation/contract separately.
Mocks validate structure, not actual AWSCC tag propagation or permission execution.

IAM service role resources: one role and one inline policy, no attachment to existing
roles and no provider changes. No live ARN is recorded from a planned output. Bind
cloudformation_role_arn only after explicit creation approval and read-only GetRole,
policy and state-owner checks. Producer certificate
0c9637e22245804a6da20f3a6b888420b4057b4d52862947ee0c9a485a8551f0 stays inactive/unattached;
ATOM certificates/policies remain preserved.

## Lifecycle, verification and costs

Read-only inventory first; planned bootstrap integration second; human saved-plan
approval before any role/policy creation. IAM has no direct role hourly charge;
underlying AWSCC-created services incur their published usage/storage costs. No
new compute or paid service is introduced by this module. CloudTrail is the existing
account audit source; new trail/log infrastructure is not added. No production claim.

Run backend-disabled init/validate and terraform test in a disposable copy. Tests
are mock-provider plan-only and cover trust, account rejection, tag fences, exact
rule/PassRole and absence of MQTT/ingestion rights. Full repository verification
is also required. No live IAM plan or API mutation is part of those checks.

Teardown: review operational resources/history and pending Cloud Control operations
before a separately approved destroy plan; retain role until all resources needing
it are removed/retained and no operation is pending. IAM deletion is not data rollback.
Undo proposed source while un-deployed by removing module; after deployment use
same-owner fresh reviewed plan, never manual state removal. Shared infrastructure,
ATOM, existing Identity Center and producer keys are out of scope.

Remaining blockers: exact name/state ownership,
request-tag compatibility, verified role/caller permissions, alias/history/native rule
and log inventory, readable resolved operational SSM (publication separate approval),
and adequate read-only provider refresh access. No operational saved plan generated.

Sources:
https://docs.aws.amazon.com/cloudcontrolapi/latest/userguide/resource-operations.html
https://docs.aws.amazon.com/service-authorization/latest/reference/list_cloudcontrol.html
https://docs.aws.amazon.com/service-authorization/latest/reference/list_iotsitewise.html
Pinned schemas: https://github.com/hashicorp/terraform-provider-awscc/tree/v1.106.0/internal/service/cloudformation/schemas

## Deleted-asset polling correction

The M1 compatibility experiment independently established native DeleteAsset accepted
under this role at 2026-10-18T18:56:08Z (event868c6244-d2d9-4c18-895d-6f59d631d85b),
then Cloud Control delete FAILED on DescribeAsset at18:56:13Z (request token
7bb8e57d-ce4a-4126-8074-7316bb40a944, native requestID
d4f6a3e5-aa4f-43af-be20-083e07928bb4). Native subsequent DescribeAsset was NotFound.
Raw records remain private; no invented successful Cloud Control deletion receipt.
The exact denied request is absent from captured CloudTrail but retained in terminal
Cloud Control status. Tag context loss after deletion is strongly supported; AWS's
internal IAM evaluation context is not directly observable here.

The existing OwnedAssetLifecycle already grants DescribeAsset, requiring ownership
tags that a deleted resource cannot supply. Add ONLY DescribeAsset in a separate
read-only AssetDeletionPolling statement, with asset ARN namespace restricted to
623155450153/us-east-1 and matching PrincipalAccount/RequestedRegion. No Resource *.
Asset ARNs contain generated UUIDs, not project/name prefixes. Exact-ID scoping
would require IDs before creation or a later policy update before each delete;
referencing operational resource outputs in their own Cloud Control role policy
introduces a bootstrap/dependency cycle and cannot support the initial lifecycle.
ResourceTag, name and hierarchy conditions cannot reliably authorize the final
missing-object status read. The fixed asset namespace is the narrowest reliable
single-pass scope supported by current AWSCC-generated IDs and native DescribeAsset.

Security tradeoff: this service role can now describe ANY asset in that account/region,
including untagged and unrelated assets, if an identifier is supplied. Metadata
includes asset properties; it is not telemetry-value read permission. This is explicit
read exposure requiring human policy review, not an ownership guarantee. No list,
model Describe, property-value read, DisassociateAssets or additional write/delete/tag
rights are granted. All previous seven statements, trust and PassRole stay unchanged.
Do not broaden other polling actions without actual handler evidence. Model deletion
was native-admin in the experiment; model AWSCC lifecycle remains unproven. This
fix has mock policy verification only; it does not claim live cleanup success.

Return to Stage2 planning after merge: use published operational SSMv2 and the canonical
state. Expected plan now has NINE operational additions AND ONE existing handler-policy
update, with TWO existing resources unchanged. The former nine-add/three-no-op scope
is superseded explicitly, not silently. Review that policy update separately or in the
same exact saved plan; no apply is authorized. Applying no policy correction yet means
the old observed cleanup risk persists. No plan regeneration, deployment or repeated
experiment is performed by this PR. Rollback is a new reviewed same-owner plan removing
only this read statement; doing so restores the known polling risk. No paid services
or additional recurring infrastructure introduced by this policy correction.
