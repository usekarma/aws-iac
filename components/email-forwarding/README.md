# Incomplete email-forwarding prototype

This component is intentionally blocked by components/status.json and deploy.sh.
Its source references an application repository as a Terraform module, passes unsupported
arguments and references undeclared Lambda resources. No current aws-config instances
use it. Original source is retained for investigation; syntax/format checks still run.
CI asserts that quarantined Terraform stays semantically unchanged. Explicit provider
validation of this component fails closed. It cannot be planned/applied/destroyed through
the deployment wrapper. A reviewed implementation spec and successful provider validation
are required before changing its readiness status. Do not guess Lambda/IAM/SES resources
just to make validation pass. This status is a safety restriction, not deployment approval.
