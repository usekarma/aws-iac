# Lambda Component

This Terraform component creates placeholder AWS Lambda functions based on a JSON config from SSM Parameter Store. These functions are meant to be deployed separately using an external process (e.g. `deploy_lambda.py` in the Karma repo).

---

## Purpose

This component registers Lambda functions by nickname, so other components (e.g. `serverless-api`) can reference them dynamically. It does **not** manage Lambda source code or deployments directly.

---

## Inputs

### Required

- `iac_prefix` – Base path for SSM parameters (e.g. `/iac`)
- `component_name` – Typically set to `lambda`
- `nickname` – Project-specific nickname (e.g. `karma-api`)

---

## Expected Config

This component expects a JSON object at:

```
/<iac_prefix>/<component_name>/<nickname>/config
```

Example:

```json
{
  "functions": {
    "karma-log-handler": {
      "runtime": "python3.10",
      "handler": "main.handler",
      "memory_size": 128,
      "timeout": 10
    },
    "karma-graph-query": {
      "runtime": "python3.10",
      "handler": "main.handler",
      "memory_size": 128,
      "timeout": 10
    }
  },
  "tags": {
    "Project": "karma"
  }
}
```

---

## What It Does

For each function defined in `functions`, it:

1. Creates an IAM role for Lambda execution
2. Attaches `AWSLambdaBasicExecutionRole` policy
3. Creates a placeholder `aws_lambda_function` with an empty ZIP
   - This function is intended to be updated manually via an external deploy script
4. Writes a runtime SSM parameter:

```
/<iac_prefix>/<component_name>/<lambda_nickname>/runtime
```

This parameter includes:

```json
{
  "function_name": "karma-log-handler",
  "placeholder": true
}
```

---

## Notes

- The actual Lambda ZIP deployment is expected to be handled outside Terraform.
- This component enables dynamic resolution and modular references via SSM paths.
- A common pattern is to use `deploy_lambda.py` from the source repo to publish versions and update the runtime parameter.
