# Config-driven Lambda component

This component reads a `functions` map from the existing SSM config path and
uses aws-iac's shared `modules/lambda` infrastructure. Declarations provide
runtime, handler, memory, timeout, retention and explicit versioned S3 artifact;
optional environment/discovery/VPC metadata retains existing conventions.
IAM, network resolution, logging, runtime SSM values and deployment stay in aws-iac.
Runtime source/testing/packaging stays in aws-lambda; desired state stays in aws-config.

There is no placeholder ZIP, local source lookup, external code deployment owner,
or runtime SSM ignore_changes. Generic runtime paths remain
`/<prefix>/lambda/<service>/runtime` and include real ARN/invoke ARN/artifact metadata.
See [the handoff contract](../../docs/lambda-artifact-contract.md) for required
schema migration, explicit publishing gap, state/log ownership review and validation.
Current legacy configs require real artifact declarations before planning.
