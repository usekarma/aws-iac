#!/usr/bin/env python3
"""Verify that this aws-iac revision supports an aws-config contract version."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY_PATH = ROOT / "contracts" / "aws-config-compatibility.json"


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"Missing contract file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def check_compatibility(aws_config_dir):
    compatibility = load_json(COMPATIBILITY_PATH)
    contract_path = Path(aws_config_dir) / "contracts" / "config-contract.json"
    contract = load_json(contract_path)

    if compatibility.get("contract_name") != "aws-config":
        raise ValueError("aws-iac compatibility contract_name must be aws-config")
    if contract.get("contract_name") != "aws-config":
        raise ValueError("aws-config contract_name must be aws-config")

    supported = compatibility.get("supported_contract_versions")
    if not isinstance(supported, list) or not supported or any(
        not isinstance(version, int) or version < 1 for version in supported
    ):
        raise ValueError("supported_contract_versions must be a non-empty list of positive integers")

    version = contract.get("contract_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("aws-config contract_version must be a positive integer")
    if version not in supported:
        raise ValueError(
            f"Unsupported aws-config contract version {version}; aws-iac supports {supported}"
        )
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aws-config-dir", required=True, type=Path)
    args = parser.parse_args()
    version = check_compatibility(args.aws_config_dir)
    print(f"Compatible aws-config contract version: {version}")


if __name__ == "__main__":
    main()
