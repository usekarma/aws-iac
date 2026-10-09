# Destructive-operation policy

An agent can prepare a destroy plan and analyze it. Execution requires explicit human
approval of the concrete plan/target. A spec, Git commit, CI pass or environment variable
does not authorize deletion. Any changed plan/config/target requires renewed review.

Before requesting approval record:

1. AWS account ID, named profile, explicit region, environment type/binding, prefix.
2. Component/nickname and exact state key; related config/IaC commit IDs.
3. Every Terraform address/action and AWS ID expected to disappear; replacements count.
4. Persistent storage IDs, sizes, contents and loss implications (including root volumes).
5. Snapshot/AMI/backup IDs, location, age, retention, restore test and recovery limits.
6. Shared dependencies and resources explicitly expected to survive.
7. Estimated blast radius, downtime, cost reduction, stop conditions and recovery steps.
8. Private plan location/digest, review time, approver and the approval decision.

Inspect resource actions and deletion of in-module S3 objects/logs as well as EC2/EBS.
Do not assume a bucket survival means all of its objects survive. Do not automatically
delete orphaned volumes, snapshots, AMIs, EIPs or NAT gateways found after teardown.
Inventory first; deletion is a separate reviewed/approved change.

## Read-only postflight

Use the exact approved account/region and rerun preflight. In aws-iac run
`./scripts/inventory.sh` to inspect EC2, EBS, load balancers, NAT gateways, EIPs,
self-owned snapshots and AMIs. This returns account-wide metadata: shared objects
are not deletion candidates merely because they are listed. Keep reports private.
Cross-reference explicit preflight IDs and plan addresses; Name tags alone are incomplete.
Check ECS services/tasks, target health, DNS/SSM runtime and S3 backup paths when relevant.
Compare a fresh read-only plan with intended IaC state (no state repair or refresh command).
Observe service health, error rates and costs during a stated window.

For config-only publishing: compare the selected SSM parameter to the approved local
JSON privately; verify version and environment binding, then plan downstream infrastructure.
The existing `validate_account_environment.py --env <binding-name>` can compare the
binding. `read_config.py` prints full values: do not use it for secret-bearing parameters.
Postflight failures stop further work; they do not authorize corrective mutations.
