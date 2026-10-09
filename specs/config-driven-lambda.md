# Config-driven Lambda infrastructure

Status: implementation for review; no release/deployment authorization.
Stakeholder: maintainers integrating tested aws-lambda runtimes through aws-config.
Baseline: generic/IoT components package empty.zip; generic code and runtime SSM
ownership are delegated out of band. IoT environment mismatches the real runtime.
Target: both consumers use one infrastructure module and explicit artifact versions;
invalid/missing artifact declarations fail; infrastructure wiring remains authoritative.

Scope: aws-iac shared module, declaration interface/checker, generic/IoT wiring,
resource moves, disposable validation packaging, tests and documentation.
Out of scope: aws-lambda changes, config publication, artifact publishing, AWS calls,
accounts/profiles, certificate attachments, TwinMaker, apply/destroy behavior.

Decisions:
- A versioned S3 object plus raw ZIP base64 SHA256 uses Lambda's native interface.
  Do not invent a publishing service, fetch local sibling ZIPs or choose a bucket.
- Declaration map keys are logical service names; IoT retains ingest_lambda_name.
  Workload sizing/environment/retention are desired state. IAM documents, roles,
  resource-derived env, VPC resolution and triggers remain infrastructure-owned.
- Share modules/lambda across consumers; preserve layout in disposable provider
  checks and use Terragrunt repo-root//component packaging for relative modules.
- Preserve existing Lambda/log identities through moved blocks; no manual state
  commands. Generic runtime SSM now reports real ARN/artifact and stays Terraform-owned.
- Narrow IoT DynamoDB actions to PutItem (actual runtime requirement) and SSM reads
  to the exact component config. No broadening or runtime-source changes.
- Runtime sequence/received_at metadata replaces placeholder attribute assumptions.

Acceptance IDs:
LAM-01 declared runtime/handler, sizing, artifact and retention reach resources.
LAM-02 missing/unversioned/placeholder artifacts fail; no local ZIP fallback.
LAM-03 IAM/authority/commands rejected by declaration schema; roles are IaC inputs.
LAM-04 derived environment wins collisions; IoT exact principal is explicit.
LAM-05 trusted topic/principal injection, source ARN/account and conditional-state
  runtime contract preserved; original IoT config tests continue to pass.
LAM-06 mocked provider plans verify resources without cloud calls; existing guards pass.
LAM-07 source packaging includes the shared module; affected provider validation passes.

Unknowns: artifact storage/publishing/region/KMS/access/digest provenance, exact
principal association, desired-state schema adoption/migration, existing live state
and external deployment consumers. No identity or approval is inferred.
Missing declaration blocks planning; input version/digest do not prove package contents.
Rollback: revert repository proposal before deployment. A later deployed rollback
requires prior reviewed artifact version and fresh approved plan; data recovery is separate.

Coordinated compatibility correction: merged aws-config/main 8637a8ae exposes
an explicit artifact-null draft with planning_dependencies. Structural checker
accepts only this declared blocked form; --require-resolved and Terraform still
reject unresolved deployment inputs. Tests compare schemas across the explicit
checkout. No artifact or identity values are manufactured. Contract version stays 1.
