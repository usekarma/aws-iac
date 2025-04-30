#!/usr/bin/env python3

import boto3
import json
import sys
from urllib.parse import urlparse

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

def get_ssm_parameter(name):
    response = ssm.get_parameter(Name=name)
    return json.loads(response["Parameter"]["Value"])

def fetch_s3_object(s3_url):
    parsed = urlparse(s3_url)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")

def main():
    query = json.load(sys.stdin)

    iac_base = query["iac_base"]
    component = query["component"]
    nickname = query["nickname"]

    base_path = f"{iac_base}/{component}/{nickname}"

    # Step 1: Get the main component config
    config = get_ssm_parameter(f"{base_path}/config")
    openapi_nickname = config["openapi"]

    # Step 2: Lookup OpenAPI pointer
    openapi_path = f"{iac_base}/openapi/{openapi_nickname}/config"
    openapi_config = get_ssm_parameter(openapi_path)

    source = openapi_config.get("source")
    inline_definition = openapi_config.get("definition")

    if source and source.startswith("s3://"):
        openapi_definition = fetch_s3_object(source)
    elif source and source.startswith("/"):
        openapi_definition = get_ssm_parameter(source)
    elif source == "inline" and inline_definition:
        openapi_definition = inline_definition
    else:
        raise Exception("Invalid OpenAPI source config")

    openapi = json.loads(openapi_definition)
    lambda_integrations = {}

    for path, methods in openapi.get("paths", {}).items():
        for method, operation in methods.items():
            nickname = operation.get("x-lambda-nickname")
            if nickname:
                lambda_arn_path = f"{iac_base}/lambda/{nickname}/runtime"
                lambda_arn = get_ssm_parameter(lambda_arn_path)
                route_key = f"{method.upper()} {path}"
                lambda_integrations[route_key] = lambda_arn

    json.dump({
        "lambda_integrations": lambda_integrations,
        "openapi_definition": openapi_definition
    }, sys.stdout)

if __name__ == "__main__":
    main()
