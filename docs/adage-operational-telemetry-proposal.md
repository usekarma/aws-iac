# Proposed SiteWise and Managed Grafana infrastructure slice

Design only; no Terraform, IAM or deployment behavior changes. Companion specification:
iot-digital-twin/docs/adage-operational-telemetry-experiment.md. Canonical consolidation
aws-iac #16 / aws-config #8 is still open; preserve that work and resolve compatibility
before implementation. The active physical device is ATOM Lite; local Python sends
synthetic telemetry initially. This path does not complete physical reset/ACK acceptance.

## Reuse and gaps

Reuse Terraform/Terragrunt backend isolation, config/runtime SSM bridge, preflight,
mock-provider/security checks, saved-plan review and human execution boundary. Existing
components/iot-digital-twin is Core2 on main, with ATOM consolidation pending #16;
add an explicitly configured operational mode there after review, not a per-experiment
component. Shared SiteWise and Managed Grafana capabilities may be small reusable
modules/components with independently owned state; decide their boundary from reuse,
not experiment names. Existing components/grafana is EC2/Kafka Connect/ALB, not AMG;
no VPC, EC2, NAT, Kafka or ClickHouse dependency is needed here.

## Minimum resources and dependencies

M1: one SiteWise asset model with INTEGER severity measurement, one asset and property
binding; one exact-topic IoT rule using native iotSiteWise action; one rule execution
role allowing BatchPutAssetPropertyValue on reviewed assets/aliases; bounded rule error
CloudWatch log group/action and its scoped role permissions. A separately approved
local-producer Thing/certificate/policy attachment is required if no suitable existing
identity exists. Never use ATOM credentials on the laptop or generate/store private
keys with Terraform. Validate alias/asset-property lifecycle against the pinned provider;
if unsupported, report the specific gap before proposing an API adapter/provider.

Publish schema/region/IDs/aliases in /iac/<capability>/<nickname>/runtime. Active consumer
reads /iac/iot-digital-twin/operational-demo/config and only the declared dependency
runtime paths; state key iot-digital-twin/operational-demo/terraform.tfstate. Do not
reuse atom-lite-001/Core2 state or import shared bucket ownership. Preserve simulator
runtime/reset resources and IAM unchanged in their existing state/config mode.

M2: expand to five assets and three measurements (severity, epoch, sequence); one
Amazon Managed Grafana workspace, existing approved Identity Center or SAML auth,
customer-managed SiteWise read role, user/role association and manually approved
versioned datasource/dashboard import. Account-wide discovery permissions, if required,
are enumerated/reviewed separately from asset-scoped property/history reads. Grafana
has no telemetry write/reset privilege. Workspace creation is not dashboard provisioning.
No SiteWise Monitor portal or physical device change. Direct native ingestion is the
initial slice; add aws-lambda validation only if a demonstrated trust/order requirement
cannot be enforced by fixed topic mappings, predicates and publisher contract.

## Security and acceptance

Local MQTT policy: exact client ID and allowlisted publish topics; no arbitrary aliases,
no subscribe/reset permissions in M1. TLS endpoint/root CA and private key are local
operator bindings. IoT role trusts iot.amazonaws.com with source-account/rule constraints
where supported. Rule error logging is observable; malformed predicates and failures
must not be mistaken for success. Independent reader gets DescribeAsset and bounded
GetAssetPropertyValue/GetAssetPropertyValueHistory (batch equivalents only if used);
list discovery is separate and minimal. Verify actual resource ARN/alias condition
support in pinned provider/AWS docs instead of silently falling back to wildcard access.

Mock tests: assets/types/topic mappings, scoped rule IAM/log permissions, unauthorized
alias inputs, trust, datasource read-only privileges and no cross-mode resource creation.
Local adapter tests belong to iot-digital-twin. Validate provider without backend/AWS,
then saved plan only with confirmed read-only target. Live M1 publishes 20 values and
reads expected history independently; target 19/20 within 10 seconds, all within 60.
QoS duplicates are possible; no sequence-fencing/exactly-once claim. M2 screen evidence
shows five assets, operational history and stale publisher indication. These proposed
checks are not implemented or passed by this documentation change.

Prior read-only evidence verified account 623155450153 with us-east-1 requests and
no current iot-digital-twin state objects; application inventory was denied. Obtain
authorized exact resource ownership and reconcile conflicts BEFORE deployment.
The artifact bucket exists and is owned by separate s3-bucket state; preserve it,
backend and Identity Center. AccessDenied never proves absence. No state migration
or permission expansion is part of this proposal.

## Costs, retention, future work and teardown

Bounded 5-asset, 1Hz, 10-minute/day use is 90k publications / up to 270k property values
per 30 days. IoT/SiteWise ingest is roughly $0.36 using published reference examples;
reserve $2 for small retrieval/storage/rule/log usage. Managed Grafana adds $9 editor,
$5 optional viewer and possibly $9 automation identity/month; minimum editor licensing
applies per workspace. Proposed total $15–25/month and $30 alert, not a hard cap;
recalculate rates/usage for the actual saved plan. No free-tier assumption. Sources:
[IoT](https://aws.amazon.com/iot-core/pricing/), [SiteWise](https://aws.amazon.com/iot-sitewise/pricing/),
[Grafana](https://aws.amazon.com/grafana/pricing/).

SiteWise is operational history; no account-level storage/tier changes in M1. A future
finite window needs explicit tier/retention/data-loss review; default storage can be
indefinite. Keep Snowflake long-term history as a separate future parallel IoT rule ->
Kinesis -> chosen ingestion bridge, with deduplication, reconciliation and backfill.
Future TwinMaker adds equipment relationships over stable SiteWise IDs. Neither future
path gates M1/M2 or creates current resources. See [native rule action](https://docs.aws.amazon.com/iot-sitewise/latest/userguide/configure-rule-action.html)
and [retention constraints](https://docs.aws.amazon.com/iot-sitewise/latest/userguide/configure-storage.html).

Teardown: stop local producer/disable owned routing, retain/export required evidence and
history; remove owned dashboard/workspace, assets/model/rule/role/logs and new producer
identity only under a reviewed destroy plan. Preserve all shared state/artifacts/auth
and existing ATOM credentials. Review data deletion, licensing timing and remaining costs.
