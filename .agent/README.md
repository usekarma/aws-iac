# aws-iac role contracts

These are repository-specific responsibilities for people or assisted sessions,
not autonomous daemons. Follow AGENTS.md and the current human work request.
aws-config owns desired state; aws-iac implements it through existing components,
SSM dependency conventions, Terraform/Terragrunt and deployment guards.

Sequence: Architect → Builder → Verifier → Reviewer → Security → Operations.
Each role supplies concise evidence, unresolved blockers and required decisions.
The local runner consumes those reports; it does not pretend to perform semantic
reviews, generate code or independently attest human authorization.

All roles stop on scope ambiguity, invented identity/secret material, requests to
broaden permissions as a fallback, or any attempted mutation without separately
reviewed human authorization. Preserve AGENT_MODE=1 and existing preflight and
AWS_MUTATION_APPROVED semantics. Environment flags and report fields do not prove
approval. No role may select an account/production profile, apply/destroy,
use auto-approval, mutate/bootstrap state, issue certificates, create/rotate
secrets, merge or push automatically. Repository edits authorized by the human
request are separate from approval for AWS changes.

See [the bounded runner guide](../docs/bounded-agent-workflow.md). The runner has
no cloud execution path, including live planning. A separately reviewed verifier
session may use scripts/plan.sh after independently confirmed identity/preflight.


For existing-component observation, use `--evaluate COMPONENT`; Builder and
remediation are omitted. Evaluation still runs the existing gates and requires
honest supplied review findings, then STOP_FOR_HUMAN. See the guide for exact
IoT and ClickHouse commands. No component fixes occur in evaluation mode.
