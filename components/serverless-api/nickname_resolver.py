#!/usr/bin/env python3

import boto3
import json
import sys
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    print("❌ Missing dependency: PyYAML. Install with `pip install pyyaml`", file=sys.stderr)
    sys.exit(1)

ssm = boto3.client("ssm")
s3 = boto3.client("s3")


def get_ssm_parameter(name):
    try:
        response = ssm.get_parameter(Name=name)
        value = response["Parameter"]["Value"]
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    except Exception as e:
        print(f"❌ Error fetching SSM parameter {name}: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_s3_object(s3_url):
    parsed = urlparse(s3_url)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except Exception as e:
        print(f"❌ Error fetching S3 object {s3_url}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    query = json.load(sys.stdin)
    iac_base = query["iac_base"]
    component = query["component"]
    nickname = query["nickname"]
    base_path = f"{iac_base}/{component}/{nickname}"

    # Step 1: Resolve component config
    config = get_ssm_parameter(f"{base_path}/config")
    openapi_nickname = config.get("openapi")
    if not openapi_nickname:
        print("❌ Missing 'openapi' field in config", file=sys.stderr)
        sys.exit(1)

    # Step 2: Get OpenAPI source location
    openapi_config = get_ssm_parameter(f"{iac_base}/openapi/{openapi_nickname}/runtime")
    source = openapi_config.get("source")
    inline_definition = openapi_config.get("definition")

    if source and source.startswith("s3://"):
        openapi_text = fetch_s3_object(source)
    elif source and source.startswith("/"):
        openapi_text = get_ssm_parameter(source)
    elif source == "inline" and inline_definition:
        openapi_text = json.dumps(inline_definition)
    else:
        print("❌ Invalid OpenAPI source runtime", file=sys.stderr)
        sys.exit(1)

    try:
        openapi = yaml.safe_load(openapi_text)
    except Exception as e:
        print(f"❌ Failed to parse OpenAPI YAML: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 3: Resolve Lambda nicknames
    lambda_integrations = {}
    for path, methods in openapi.get("paths", {}).items():
        for method, operation in methods.items():
            nickname = operation.get("x-lambda-nickname")
            if nickname:
                lambda_runtime_path = f"{iac_base}/lambda/{nickname}/runtime"
                runtime_data = get_ssm_parameter(lambda_runtime_path)

                if isinstance(runtime_data, dict) and "arn" in runtime_data:
                    lambda_arn = runtime_data["arn"]
                elif isinstance(runtime_data, str):
                    lambda_arn = runtime_data
                else:
                    print(f"❌ Lambda '{nickname}' is missing a valid runtime ARN.", file=sys.stderr)
                    print(f"SSM value at {lambda_runtime_path} = {json.dumps(runtime_data, indent=2)}", file=sys.stderr)
                    print("💡 Hint: Run `deploy_lambda.py {nickname}` before deploying the API.", file=sys.stderr)
                    sys.exit(1)

                route_key = f"{method.upper()} {path}"
                lambda_integrations[route_key] = lambda_arn

    if not lambda_integrations:
        print("❌ No Lambda nicknames resolved from OpenAPI", file=sys.stderr)
        sys.exit(1)

    json.dump({
        "lambda_integrations": json.dumps(lambda_integrations)
    }, sys.stdout)


if __name__ == "__main__":
    main()
