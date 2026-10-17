# iot-digital-twin-simulator wiring — review only

Companion to aws-lambda's durable demo runtime, not the Core2 component. Reads explicit
SSM config fields: artifact (versioned S3 ZIP metadata), model_commit, active_session,
expected_principal. No value-bearing config, account/principal or artifact is invented.
aws-config must adopt/validate this new component before any publication or saved plan.

Creates a PK/SK sandbox DynamoDB table, two Lambdas/roles/log groups, exact reset IoT
rule and scoped invocation permission. Runner supports supervised operation=start and
180-second execution; reset handler publishes committed receipts on the exact ACK topic.
IAM allows item operations only on the table/current session partition; IoT Publish
belongs only to reset. No certificate, device policy, frontend/public endpoint, SSM write,
artifact upload or AWS operation is performed by adding this source.

The device's subscription/publish policy amendment remains separately reviewed work.
Account/region binding, artifact publication, sdk adapter integration, operator invoke
permissions, alerts and cost evidence must be resolved before a live saved plan.
Do not apply. Preserve receipts for separately approved teardown. Full repository gates
and terraform validation must pass before review approval. No production readiness claim.

Observed local verification: Terraform 1.15.2 / signed AWS provider 6.69.1;
backend-disabled init/validate passed. One mock-provider test passed, asserting
runner bounds, reset routing, separated publish privilege and session-scoped storage.
Full scripts/verify.sh --terraform iot-interview-demo passed using explicit
AWS_CONFIG_DIR=/home/ted/dev/aws-config, existing locked Python tooling and temporary
distro shellcheck 0.9.0. Repository suite ran 154 tests (one pre-existing skip).
Initial checks failed on missing shellcheck/config checkout and unknown/invalid mock
ARN values; those environment/fixture issues were corrected without weakening gates.
No live plan, AWS identity check, apply, permission change or resource mutation occurred.

Naming revision: table, functions, roles, logs and rule use the simulator component
name. Tags are Project=iot-digital-twin, Experiment=atom-lite-simulator and
Environment=sandbox. Existing Core2 names, topics, IAM restrictions and runtime
contracts are preserved. header.tf now holds declarations required by aws-config
validation; resource addresses are unchanged. Rechecked the complete repository
gates (154 tests, one existing skip), init/validate and the mock-provider test,
including tag assertions, using /tmp/aws-simulator-config-checkout as AWS_CONFIG_DIR.
These proposed names have not been deployed or checked against live AWS inventory.
