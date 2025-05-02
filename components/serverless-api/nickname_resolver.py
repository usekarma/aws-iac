#!/usr/bin/env python3

import boto3
import json
import sys
import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate and print resolved mappings without outputting JSON")
    args = parser.parse_args()

    query = json.load(sys.stdin)
    iac_base = query["iac_base"]
    nickname = query["nickname"]

    openapi_runtime = get_ssm_parameter(f"{iac_base}/openapi/{nickname}/runtime")
    source = openapi_runtime.get("source")
    inline_definition = openapi_runtime.get("definition")

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

    lambda_integrations = {}
    for path, methods in openapi.get("paths", {}).items():
        for method, operation in methods.items():
            lambda_nick = operation.get("x-lambda-nickname")
            if lambda_nick:
                lambda_runtime_path = f"{iac_base}/lambda/{lambda_nick}/runtime"
                runtime_data = get_ssm_parameter(lambda_runtime_path)

                if isinstance(runtime_data, dict) and "arn" in runtime_data:
                    lambda_arn = runtime_data["arn"]
                elif isinstance(runtime_data, str):
                    lambda_arn = runtime_data
                else:
                    print(f"❌ Lambda '{lambda_nick}' is missing a valid runtime ARN.", file=sys.stderr)
                    sys.exit(1)

                route_key = f"{method.upper()} {path}"
                lambda_integrations[route_key] = lambda_arn

    if not lambda_integrations:
        print("❌ No Lambda nicknames resolved from OpenAPI", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("🔍 Resolved Lambda integrations:")
        for k, v in lambda_integrations.items():
            print(f"  {k}: {v}")
        sys.exit(0)

    json.dump({
        "lambda_integrations": json.dumps(lambda_integrations)
    }, sys.stdout)

if __name__ == "__main__":
    main()
