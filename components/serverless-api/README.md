# Serverless API Component

![Serverless API](../../img/serverless-api.drawio.png)

This Terraform component deploys an Amazon API Gateway **HTTP API** using an OpenAPI 3.0 definition stored in S3. Lambda integrations are resolved dynamically using nicknames in the OpenAPI spec, mapped to ARNs via SSM Parameter Store.

---

## Features

- Deploys HTTP APIs from OpenAPI 3.0+ specs
- Resolves Lambda integrations using `x-lambda-nickname` fields
- Supports custom domains via ACM and Route 53
- Stores runtime metadata in SSM Parameter Store
- Works in config-driven, multi-account AWS setups

---

## Usage

Deploy with:

```bash
AWS_PROFILE=prod-iac ./scripts/deploy.sh serverless-api karma-api --auto-approve
```

This will:

1. Read config from: `/iac/serverless-api/karma-api/config`
2. Resolve OpenAPI pointer from: `/iac/openapi/karma-api/runtime`
3. Resolve Lambda nicknames via: `/iac/lambda/<nickname>/runtime`
4. Deploy an HTTP API Gateway with integrations
5. Optionally configure a custom domain
6. Write runtime output to: `/iac/serverless-api/karma-api/runtime`

---

## Required Inputs (`/iac/serverless-api/<nickname>/config`)

```json
{
  "openapi": "karma-api",
  "stage_name": "v1",
  "domain_name": "api.usekarma.dev",
  "route53_zone_name": "usekarma.dev",
  "tags": {
    "Project": "karma"
  }
}
```

- `openapi`: nickname used to resolve the OpenAPI spec
- `domain_name` + `route53_zone_name`: optional, enable custom domain support

---

## OpenAPI Runtime Config (`/iac/openapi/<openapi>/runtime`)

Must contain a pointer to the OpenAPI spec:

```json
{
  "openapi_ref": "s3://usekarma.dev-prod-karma-api/karma-api.yaml"
}
```

In the OpenAPI file, use `x-lambda-nickname` to reference Lambda handlers:

```yaml
post:
  summary: Log an event
  operationId: logEvent
  x-lambda-nickname: log-handler
```

---

## Lambda Runtime Config (`/iac/lambda/<nickname>/runtime`)

Each referenced Lambda nickname must resolve to a versioned ARN:

```json
{
  "arn": "arn:aws:lambda:us-east-1:123456789012:function:log-handler:3"
}
```

This allows API deployments to remain stable even as Lambda code evolves.

---

## Outputs (`/iac/serverless-api/<nickname>/runtime`)

```json
{
  "api_id": "a1b2c3d4",
  "api_endpoint": "https://a1b2c3d4.execute-api.us-east-1.amazonaws.com",
  "stage_name": "v1",
  "custom_domain": "api.usekarma.dev"
}
```

These values can be consumed by frontends, CI/CD pipelines, or monitoring tools.

---

## How It Works

- The OpenAPI spec defines the API interface, not Lambda ARNs
- Lambda nicknames are resolved at deploy time using SSM
- Custom domains are created if enabled and properly configured
- This supports safe, versioned Lambda promotion without modifying the API definition

---

## Dependencies

To use custom domains, ensure:

- An ACM certificate exists for your domain (in `us-east-1`)
- A Route 53 hosted zone is configured for your domain
- DNS delegation is set up from your registrar to Route 53

---

## Notes

- OpenAPI specs must be published via a separate step (e.g., `deploy_openapi.py`)
- Only HTTP APIs are supported (not legacy REST APIs or WebSockets)
- OpenAPI must be valid v3.0.3+ and stored in S3, referenced via SSM
