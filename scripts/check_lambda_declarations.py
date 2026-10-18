#!/usr/bin/env python3
"""Validate explicit desired Lambda declarations locally; no AWS or artifact downloads."""

import argparse
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/lambda-declaration-v1.schema.json").read_text())

DRAFT_SCHEMA = copy.deepcopy(SCHEMA)
DRAFT_SCHEMA["title"] = "Incomplete Lambda planning declaration"
DRAFT_SCHEMA["properties"]["artifact"] = {"type": "null"}
DRAFT_SCHEMA["required"].append("planning_dependencies")
DRAFT_SCHEMA["properties"]["planning_dependencies"] = {
    "type": "array",
    "uniqueItems": True,
    "minItems": 1,
    "items": {"enum": ["artifact_publication", "trusted_principal"]},
    "contains": {"const": "artifact_publication"},
}


def validate_declaration(value: dict) -> None:
    """Reject missing artifact references and infrastructure/security policy fields."""
    errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
    if errors:
        raise ValueError("Invalid Lambda declaration: " + errors[0].validator)
    if any(key in value for key in ("src_type", "src_nickname")) and not all(
        key in value for key in ("src_type", "src_nickname")
    ):
        raise ValueError("Source type and nickname must be paired")
    version = value["artifact"]["s3_object_version"]
    if not version.strip():
        raise ValueError("Artifact version must be explicit")


def validate_config(value: dict, component: str, require_resolved: bool = False) -> None:
    """Validate supported consumer declarations without resolving cloud identities."""
    if component == "lambda":
        functions = value.get("functions")
        if not isinstance(functions, dict) or not functions:
            raise ValueError("Missing Lambda functions")
        for declaration in functions.values():
            validate_declaration(declaration)
    elif component == "iot-digital-twin":
        schema = json.loads((ROOT / "contracts/iot-digital-twin.schema.json").read_text())
        if list(Draft202012Validator(schema).iter_errors(value)):
            raise ValueError("Invalid simulator configuration")
        if value.get("mode") == "operational-telemetry":
            if value.get("deployment_stage") == "service-role-bootstrap":
                if require_resolved and (
                    value.get("expected_account") != "623155450153"
                    or value.get("region") != "us-east-1"
                    or "planning_dependencies" in value
                    or value.get("expected_principal") is None
                ):
                    raise ValueError("Unresolved bootstrap target/identity")
                return
            if (
                require_resolved
                and value.get("deployment_stage") == "operational"
                and not value.get("awscc_request_tags_verified")
            ):
                raise ValueError("AWSCC request-tag behavior unverified")
            unresolved = "planning_dependencies" in value or any(
                value[k] is None
                for k in (
                    "region",
                    "expected_account",
                    "expected_principal",
                    "cloudformation_role_arn",
                )
            )
            if require_resolved and unresolved:
                raise ValueError("Unresolved operational bindings")
            if (
                not unresolved
                and value["cloudformation_role_arn"].split(":")[4] != value["expected_account"]
            ):
                raise ValueError("CloudFormation role account mismatch")
            return
        if require_resolved and (
            "planning_dependencies" in value
            or any(
                value[key] is None
                for key in ("artifact", "region", "active_session", "expected_principal")
            )
        ):
            raise ValueError("Unresolved simulator bindings")
        if value["artifact"] is not None:
            import base64

            digest = value["artifact"]["source_code_hash"]
            decoded = base64.b64decode(digest, validate=True)
            if len(decoded) != 32 or base64.b64encode(decoded).decode() != digest:
                raise ValueError("Invalid simulator digest")
            if not value["artifact"]["s3_object_version"].strip():
                raise ValueError("Missing immutable artifact version")
    else:
        raise ValueError("Unsupported Lambda declaration consumer")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aws-config-dir", required=True, type=Path)
    parser.add_argument("--config-path", required=True, action="append", type=Path)
    parser.add_argument(
        "--require-resolved",
        action="store_true",
        help="Reject unresolved artifact/principal declarations before planning",
    )
    args = parser.parse_args()
    blocked = False
    checkout = args.aws_config_dir.resolve()
    for relative in args.config_path:
        source = (checkout / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) != 5
            or relative.parts[0] != "iac"
            or relative.name != "config.json"
            or not source.is_relative_to(checkout)
        ):
            raise ValueError("Expected explicit iac/environment/component/nickname/config.json")
        value = json.loads(source.read_text())
        validate_config(value, relative.parts[2], require_resolved=args.require_resolved)
        blocked |= relative.parts[2] == "iot-digital-twin" and (
            "planning_dependencies" in value or value.get("artifact") is None
        )
    if blocked:
        print(
            "Lambda declaration structurally compatible; planning BLOCKED by unresolved artifact/principal dependencies."
        )
    else:
        print("Lambda declarations valid; artifact availability and digest are NOT_VERIFIED.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError):
        raise SystemExit("Lambda declaration check failed; source/contract unavailable or invalid.")
