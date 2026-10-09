# Understanding the `aws-config` + `aws-iac` Repositories

## Purpose

These repositories work together as a controlled infrastructure system:

- **`aws-config`** defines the desired configuration and governance contracts.
- **`aws-iac`** implements those desired settings using Terraform/Terragrunt and related tooling.
- **AWS** is the actual running environment.
- **Humans** remain the authority for consequential changes.

The important design goal is not to let AI or automation freely change infrastructure. It is to let agents do as much safe preparation, analysis, validation, and evidence generation as possible while keeping real infrastructure changes behind explicit human review.

A useful mental model is:

```text
Human objective
      ↓
aws-config: what should be true
      ↓
aws-iac: how that desired state is implemented
      ↓
validation / plan / evidence
      ↓
human review and approval
      ↓
authorized execution
      ↓
post-change verification
```

---

## 1. What `aws-config` Owns

`aws-config` is the declarative side of the system.

It answers questions such as:

- Which environment or account binding is being targeted?
- Which infrastructure components should exist?
- What values are allowed for those components?
- What dependencies must exist between components?
- What governance rules define "correct"?
- What steady-state cost targets should be expected?

The configuration files are not just arbitrary JSON. They are checked against JSON Schemas and repository-level rules before they can be treated as valid configuration.

The repository therefore acts as a **contract**, not just a storage location for parameters.

---

## 2. What `aws-iac` Owns

`aws-iac` contains the implementation of infrastructure behavior.

It answers questions such as:

- What Terraform resources implement a configured component?
- How are modules wired together?
- How is a Terraform/Terragrunt plan generated?
- What will AWS actually create, change, replace, or delete?
- What infrastructure currently exists?
- What does Cost Explorer report?
- What evidence should a reviewer inspect before approving a change?

A configuration value may describe intent, but Terraform determines the actual proposed infrastructure change.

That distinction matters:

```text
aws-config says what is desired.
aws-iac says how AWS would be changed to achieve it.
Terraform plan shows the proposed reality.
A human decides whether reality is allowed to change.
```

---

## 3. Schemas Are Executable Configuration Contracts

The JSON Schemas in `aws-config` define what valid component configuration looks like.

They can enforce things such as:

- required fields
- valid data types
- allowed values
- unknown-field rejection
- CIDR formatting
- dependency references
- environment/binding consistency

The validation path is approximately:

```text
config.json
    ↓
config_validation.py
    ↓
matching component schema
    ↓
PASS / FAIL
    ↓
local verification + CI
```

This is important because schema compliance does not depend on an AI "understanding" the rules. The validation is ordinary deterministic software.

If a configuration violates a schema, verification fails.

---

## 4. Contract Versioning Between the Repositories

The schemas in `aws-config` and the input expectations in `aws-iac` must evolve together.

To prevent silent drift, the repositories now use an explicit compatibility contract.

`aws-config` declares a repository-level configuration contract version:

```json
{
  "contract_name": "aws-config",
  "contract_version": 1
}
```

`aws-iac` explicitly declares which versions it supports:

```json
{
  "contract_name": "aws-config",
  "supported_contract_versions": [1]
}
```

The rule is:

> A breaking configuration-schema change requires a new `aws-config` contract version, and `aws-iac` must explicitly declare support for that version before consuming it.

That means a future breaking schema change should look like:

```text
aws-config contract v1
        ↓
breaking schema change
        ↓
aws-config contract v2
        ↓
aws-iac reviewed/updated for v2
        ↓
aws-iac supported_contract_versions includes 2
        ↓
compatibility check passes
```

Without this handshake, two independently changing repositories could appear healthy while disagreeing about the meaning of configuration.

---

## 5. Verification Gates

Both repositories include deterministic verification gates.

These checks may include:

- Python syntax
- Ruff linting
- Ruff formatting
- shell syntax
- ShellCheck
- JSON validation
- JSON Schema validation
- duplicate-key rejection
- Terraform formatting
- Terraform validation
- Terragrunt validation
- dependency validation
- contract-version compatibility
- unit tests
- static security checks
- repository consistency checks

GitHub Actions runs these gates in CI.

These checks answer questions such as:

> Is the repository internally consistent?

> Does this configuration conform to its declared schema?

> Does `aws-iac` support this configuration contract version?

> Does the Terraform code parse and validate?

They do **not** answer:

> Is this business change a good idea?

> Is this production outage risk acceptable?

> Is it safe to delete this data?

> Should we incur this cost?

Those remain human decisions.

---

## 6. Agent Mode

Agents are expected to operate with:

```bash
AGENT_MODE=1
```

Agent mode is intended to allow safe work such as:

- reading code
- inspecting configuration
- writing code
- writing tests
- running verification
- generating Terraform plans
- inventorying resources
- analyzing costs
- generating evidence
- proposing remediation

It is intended to block or prevent normal agent workflows from performing actions such as:

- Terraform apply
- Terraform destroy
- Terragrunt apply/destroy
- automatic approval
- backend bootstrap
- configuration publication

Agent mode is an important guardrail, but it is not the ultimate security boundary.

The stronger boundary is **AWS authorization**. Read-only IAM should be used for autonomous inspection and planning whenever possible.

An environment variable can be edited. IAM permissions cannot be bypassed merely by changing an environment variable.

---

## 7. Terraform Plan Is a Review Artifact, Not an Approval

A Terraform plan is one of the most important artifacts in the workflow.

It tells the reviewer what Terraform currently proposes to do.

Typical actions include:

```text
create
update
replace
delete
no change
```

The plan should be generated after code and configuration verification and before any apply.

If the code, configuration, target account, relevant state, or plan changes, the previous approval should no longer be treated as valid.

The correct mental model is:

```text
Plan = proposed change
Approval = authorization for that exact proposed change
Apply = execution of the approved change
```

---

## 8. Evidence Exists to Help Humans Review Changes

The repository can generate structured evidence from a plan.

Evidence can summarize things such as:

- affected resources
- resource actions
- replacements
- deletions
- persistent storage risk
- IAM/network changes
- possible drift
- plan digests
- expected surviving resources
- recovery information
- postflight expectations

The purpose is to reduce the amount of raw Terraform output a human must interpret manually.

However:

> Evidence is not proof that a change is safe.

It is **structured input to human judgment**.

A reviewer should still understand the blast radius and the consequences of the proposed operation.

---

## 9. Where Human Checks Fit

Human checks are intentionally placed at the boundary between **preparation** and **consequence**.

The preferred workflow is:

```text
SPEC
  ↓
agent/human inspection
  ↓
implementation
  ↓
schemas + tests + verification
  ↓
Terraform/Terragrunt plan
  ↓
evidence generation
  ↓
HUMAN REVIEW
  ↓
HUMAN APPROVAL
  ↓
authorized apply/destroy/publication
  ↓
postflight verification
  ↓
operational observation
```

The human reviewer is responsible for checking more than whether CI passed.

At minimum, the reviewer should understand:

### Target

- Which AWS account is being affected?
- Which region?
- Which environment?
- Which binding?
- Is this production or non-production?

### Change

- What resources are being created?
- What resources are being modified?
- What resources are being replaced?
- What resources are being deleted?

### Data

- Could persistent data be lost?
- Are backups present?
- Has restore capability actually been demonstrated?
- What resources survive a teardown?

### Security

- Are IAM permissions being broadened?
- Are network boundaries changing?
- Is encryption changing?
- Is logging or monitoring being weakened?

### Operations

- What is the blast radius?
- What is the rollback or recovery path?
- What verifies success after execution?
- What should be observed after the change?

### Cost

- Will the change add persistent spend?
- Does it move the environment toward or away from its declared steady-state cost target?
- Is all recurring spend accounted for?

Passing CI is necessary evidence, but it is not sufficient authorization.

---

## 10. Approval Must Be Specific

A human approval should apply to a concrete operation and target.

For example:

```text
Approve applying plan X
to account Y
in us-east-1
for component Z.
```

A vague statement such as:

```text
go ahead
```

should not be treated as permanent approval for unrelated future operations.

Likewise:

```text
AWS_MUTATION_APPROVED=1
```

is an operator acknowledgement that approval has already occurred. It is not permission for an agent to approve itself.

Approval should be renewed if the reviewed plan changes.

---

## 11. Destructive Changes Need Stronger Review

Deletion and replacement require extra scrutiny.

Before deleting persistent infrastructure, the reviewer should know:

- exact resource identifiers
- whether data will be destroyed
- where backups live
- whether backups survive the operation
- whether restoration has been tested
- which dependent resources remain
- whether detached resources could continue costing money
- how the environment would be recovered

A destroy plan should be reviewed just as carefully as a normal apply plan.

"Terraform says delete" is not sufficient justification for deletion.

---

## 12. Postflight Verification

The work is not complete when Terraform finishes.

After an approved infrastructure change, use read-only checks to verify the expected result.

Examples:

- resource should exist
- resource should no longer exist
- SSM parameter should exist
- expected configuration keys should be present
- target account and region should still be correct

A failed permission check must not be interpreted as proof that a resource is absent.

Postflight validation provides evidence that the approved change actually produced the expected infrastructure state.

Operational observation still matters after postflight.

---

## 13. Cost Governance

The system also contains a steady-state AWS cost contract.

The current initial targets are:

```text
strall.com     $0.51/month
usekarma.dev   $0.61/month
combined       $1.12/month
```

The policy requires recurring spend to be accounted for and treats remediation as proposal-only unless separately approved.

The intended flow is:

```text
desired configuration
        +
declared cost target
        +
actual AWS inventory
        +
Cost Explorer data
        ↓
reconciliation
        ↓
variance / unexplained spend
        ↓
evidence + remediation proposal
        ↓
human review
```

The reconciler may identify a problem.

It does not automatically earn the right to delete the resource causing that problem.

---

## 14. What an Engineer Should Understand Before Approving Changes

You do not need to understand every line of every generated script.

You **do** need to understand these boundaries:

1. **What `aws-config` controls.**
2. **What `aws-iac` will do with that configuration.**
3. **Which contract version connects the two repositories.**
4. **What the schemas and CI actually prove.**
5. **What the Terraform plan proposes.**
6. **What the evidence artifact summarizes.**
7. **Which account, region, environment, and resources are targeted.**
8. **Whether persistent data, security, availability, or cost are affected.**
9. **Where explicit human approval is required.**
10. **How success is verified after execution.**

That level of understanding is enough to make AI-assisted infrastructure engineering useful without turning it into blind trust.

---

## 15. Trust Model

The system deliberately uses several layers of trust:

```text
Natural-language instructions
        ↓
guide agent behavior

Schemas / scripts / tests
        ↓
deterministically enforce repository rules

CI
        ↓
requires those checks to execute consistently

Terraform plan
        ↓
shows proposed infrastructure consequences

Evidence
        ↓
makes consequences easier to review

Human approval
        ↓
authorizes consequential execution

AWS IAM
        ↓
provides the actual technical authority boundary

Postflight checks
        ↓
verify observed outcome
```

No single layer should be treated as sufficient on its own.

The design is strongest when all of them agree.

---

## 16. The Most Important Principle

The central idea behind these repositories is:

> **The agent is allowed to propose reality. Terraform describes the proposed reality. A human still authorizes reality to change.**

That is the boundary to preserve as the repositories become more automated and more agent-driven.
