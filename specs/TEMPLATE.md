# Infrastructure work specification

Status: draft | reviewed | verified | awaiting approval | observed
Owner/reviewer:
Related repository/commit and configuration commit:

## Goal
## Business/engineering intent
Expected benefit and measurable acceptance criteria:
## Environment/account/region
Exact AWS account ID, named profile, region, environment type, binding name,
component/nickname, IAC_PREFIX, and state key. Do not infer environment from nickname.
## In scope
## Out of scope
## Resources expected to change
Resource addresses/IDs; additions, changes, replacements, deletions; config parameter paths.
## Resources/data that must be preserved
Persistent volumes, S3 objects, snapshots, AMIs, backups, shared dependencies, state backend.
## Security considerations
IAM, network exposure, encryption, secret handling; explain any control change.
## Operational considerations
Owner, logging/metrics/alarms, health checks, tags, cost impact, downtime, backups.
Use N/A with a reason where a requirement does not apply.
## Failure/recovery strategy
Blast radius, stop conditions, backup age and recovery test evidence, recovery time.
## Verification
Exact local gate commands, plan acceptance criteria, read-only postflight checks.
Record commands, outcomes, commit IDs, timestamp, and unresolved findings.
## Rollback
Config version restore and new reviewed plan; data restoration is separate from redeployment.
## Human approval requirements
Exact operation/target, reviewed plan digest, resource/data impact, approver and decision.
A draft spec or approval acknowledgement variable is not human authorization.
