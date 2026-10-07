# Example: unused ClickHouse stack cleanup in usekarma-dev

Status: **illustrative draft — no live inventory/plan/approval; execute nothing**

## Goal
Remove an unused analytics stack and its recurring compute/storage cost.
## Business/engineering intent
Reduce waste while preserving recovery material and shared infrastructure.
## Environment/account/region
Candidate profile prod-karma; region us-east-1; binding usekarma-dev-prod;
environment type prod; nickname usekarma-dev; component clickhouse; prefix /iac.
Account ID MUST be independently confirmed before planning. State key:
clickhouse/usekarma-dev/terraform.tfstate. Reconcile live state first: the deployment
may already be removed. Do not recreate it just to test this example.
## In scope
Only resources owned by the clickhouse component in that exact state.
## Out of scope
VPC, shared ECS cluster, S3 bucket, Cognito, Route53 zone, APIs and other accounts.
## Resources expected to change
Candidate addresses from current code (actual plan determines presence/count):
aws_instance.clickhouse, aws_instance.mongo[0], aws_instance.redpanda[0];
aws_ebs_volume.data, aws_ebs_volume.mongo_data[0], aws_ebs_volume.redpanda_data[0];
volume attachments, stack ALB/targets/listeners/DNS records, ECS services/task
definitions, log groups, IAM roles/policies, security rules, runtime SSM parameter
and in-module bootstrap/schema/dashboard S3 objects. Review every plan address.
## Resources/data that must be preserved
Shared VPC/subnets/endpoints, ECS cluster, S3 bucket and actual backup objects,
Cognito, parent DNS zone, state bucket/lock table, externally managed config parameters.
Self-owned snapshots/AMIs survive this component destroy unless present in actual plan;
verify identifiers and references. Bootstrap S3 objects owned by this module are deleted.
## Security considerations
No IAM/network relaxation. Sensitive Mongo connection details may be in state/plan.
## Operational considerations
Code defaults: ClickHouse data 500 GiB, MongoDB 300 GiB, Redpanda 200 GiB;
live SSM overrides may differ. All three data EBS resources are owned by this module;
destroy can delete them. Record actual IDs, root volumes, sizes, backups and restore tests.
Identify callers of the ALB/services before approval; estimate actual savings from inventory.
## Failure/recovery strategy
Stop on unexpected shared-resource deletion, unknown storage content or missing restore
evidence. Backup creation is itself a mutation requiring separate approval. Redeploying
EC2 does not restore deleted volumes. Specify backup age and restoration procedure.
## Verification
1. Record both repo revisions and inventory; confirm binding/account/region.
2. Run both ./scripts/verify.sh; in aws-iac also --terraform clickhouse.
3. Run aws-iac ./scripts/preflight.sh and ./scripts/inventory.sh privately.
4. Run ./scripts/plan.sh clickhouse usekarma-dev --destroy.
5. Review private plan resource actions/IDs and protected-resource list. Record digest.
6. Request explicit human approval for the exact deletion/data-loss scope. Stop here.
7. After approved execution, rerun inventory and query exact preflight IDs. Check
   detached EBS, ALBs, NAT/EIPs, snapshots/AMIs, ECS, DNS and S3 recovery objects.
   Prove shared dependencies and backup objects survive; investigate any leftovers.
## Rollback
Approved redeployment plus explicit backup restoration; define recovery time/loss window.
## Human approval requirements
No approval exists for this example. Approval must name target, plan digest, affected
volumes and data impact. Do not run ch-down.sh, which also destroys shared VPC/ECS.
