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
        declaration = value.get("ingest_function")
        draft = isinstance(declaration, dict) and declaration.get("artifact", "missing") is None
        if draft and not require_resolved:
            if list(Draft202012Validator(DRAFT_SCHEMA).iter_errors(declaration)):
                raise ValueError("Invalid explicitly blocked IoT declaration")
            if (
                not declaration.get("environment", {}).get("EXPECTED_PRINCIPAL", "").strip()
                and "trusted_principal" not in declaration["planning_dependencies"]
            ):
                raise ValueError("Missing trusted-principal planning dependency")
        else:
            validate_declaration(declaration)
        if (
            declaration["runtime"] != "python3.12"
            or declaration["handler"] != "app.lambda_handler"
            or (
                not draft
                and (
                    Path(declaration["artifact"]["s3_key"]).name != "iot-digital-twin-ingest.zip"
                    or not declaration.get("environment", {}).get("EXPECTED_PRINCIPAL", "").strip()
                )
            )
            or value.get("mqtt_topic") != f"devices/{value.get('device_id')}/telemetry"
            or declaration["log_retention_days"] != value.get("cloudwatch_log_retention_days")
        ):
            raise ValueError("IoT runtime, identity/topic or retention contract mismatch")
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
        blocked |= (
            relative.parts[2] == "iot-digital-twin" and value["ingest_function"]["artifact"] is None
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
