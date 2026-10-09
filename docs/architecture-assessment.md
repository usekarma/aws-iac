# Architecture assessment and upgrade scope

Implementation inspected before this extension: aws-iac f678fee, aws-config bd959f7;
original main revisions 6c127a9 and b39afb8. Template principles inspected at 2c23b89.

## Architecture verified against code

Desired state: account_environments/<binding>.json and
 iac/<environment>/<component>/<nickname>/config.json in aws-config.
Approved publishers overwrite SSM /<prefix>/environment and /<component>/<nickname>/config.
The live binding selects the environment directory, not AWS_PROFILE or the nickname.
IAC_PREFIX defaults to /iac; both repos must agree. Binding files have no account IDs.

aws-iac root terragrunt.hcl selects components using TF_COMPONENT/TF_NICKNAME and
injects account S3 state and DynamoDB locking into an empty backend block. State key:
<component>/<nickname>/terraform.tfstate. Terraform reads config JSON and dependency
runtime JSON through SSM and writes its own runtime JSON. There is no Terragrunt DAG.
Deployment order must follow those runtime dependencies. Some aliases use us-east-1.

Implemented components: clickhouse, cognito-sso, ecs-cluster, ecs-service,
grafana, lambda, route53-zone, s3-bucket, serverless-api,
serverless-site, vpc. eks-cluster, rds-postgres and sqs-queue are documentation/examples,
not deployable modules. email-forwarding is an incomplete prototype: its external source
is application code, not a Terraform module, and it references missing Lambda resources.
It has no current config and is explicitly blocked from deployment. ClickHouse owns ClickHouse, MongoDB, Redpanda, EBS, ECS services,
ALB/DNS and observability; AMI builds and application image publication are separate.
VPC supplies subnet/security-group runtime, ECS supplies cluster runtime, S3 supplies
backup bucket runtime, Cognito supplies authentication runtime. Lambda resolves VPC
runtime and serverless-api uses a Python external data source and Lambda runtime.

## Original gaps and previous draft

Original deploy defaulted to apply with broad/non-interactive execution. Account
identity and environment selection were implicit; backend initialization could mutate
AWS during a supposed plan. Publishers wrote SSM without an approval boundary. No
first-class agent contract, common offline gate, safety regression tests or PR CI existed.
Previous draft added those guards and tests, but approval flags could override the
intended agent restriction; validation was structural only; evidence was manual.
Provider validation and legacy formatting debt remained visible but unresolved.

## Extension acceptance criteria

1. AGENT_MODE=1 blocks mutations even with operator acknowledgement, before AWS calls.
2. Validate all existing config against explicit per-component schemas; reject typos,
wrong types, missing required keys, duplicate JSON keys and unresolved local dependencies.
3. Produce private, value-free JSON/Markdown evidence from Terraform plan JSON;
identify deletes/replacements, persistent-data exposure, IAM/network review and unknowns.
4. Credential-free CI runs the same pinned local gates; no apply or SSM publishing.
5. Demonstrate objective → validation → synthetic plan → evidence → approval boundary.
6. Prepare read-only postflight comparisons; never interpret leftovers as deletion authority.
7. Preserve resource definitions and the config → SSM → Terraform → runtime architecture.

## Consequential implementation facts

Standalone EBS volumes are managed resources and can be destroyed, regardless of
instance termination settings. ClickHouse backups in a separately managed S3 bucket,
self-owned AMIs/snapshots, and detached volumes may survive and incur costs. S3 modules
can force-delete data; runtime/userdata can contain connection details. No blanket
prevent_destroy lifecycle or data-retention redesign is introduced: surface the risk.
Production readiness needs a current live plan, restore evidence and owner approval.
