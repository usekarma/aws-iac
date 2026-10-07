#!/usr/bin/env python3
"""Read-only expected-state verification after separately approved execution."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EC2 = {
    "instance": ("describe-instances", "instance-id", "Reservations", "i-"),
    "volume": ("describe-volumes", "volume-id", "Volumes", "vol-"),
    "snapshot": ("describe-snapshots", "snapshot-id", "Snapshots", "snap-"),
    "image": ("describe-images", "image-id", "Images", "ami-"),
}


def query(args):
    result = subprocess.run(
        [
            "aws",
            "--profile",
            os.environ["AWS_PROFILE"],
            "--region",
            os.environ["AWS_REGION"],
            "--no-cli-pager",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
            "--output",
            "json",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def check(expectation):
    kind, identifier = expectation["type"], expectation["id"]
    if expectation["expected"] not in ("present", "absent"):
        raise ValueError("expected must be present or absent")
    if kind in EC2:
        operation, field, collection, prefix = EC2[kind]
        if not re.fullmatch(re.escape(prefix) + r"[0-9a-f]+", identifier):
            raise ValueError("Invalid EC2 ID")
        arguments = ["ec2", operation, "--filters", f"Name={field},Values={identifier}"]
        if kind in ("snapshot", "image"):
            arguments += ["--owner-ids" if kind == "snapshot" else "--owners", "self"]
        items = query(arguments)[collection]
        if kind == "instance":
            items = [
                item
                for reservation in items
                for item in reservation["Instances"]
                if item["State"]["Name"] != "terminated"
            ]
        present = bool(items)
    elif kind == "ssm":
        prefix = os.environ.get("IAC_PREFIX", "/iac")
        if not isinstance(identifier, str) or not identifier.startswith(prefix + "/"):
            raise ValueError("SSM path must be under reviewed IAC_PREFIX")
        # Describe first: permission/transport errors must not masquerade as absence.
        items = query(
            [
                "ssm",
                "describe-parameters",
                "--parameter-filters",
                f"Key=Name,Option=Equals,Values={identifier}",
            ]
        )["Parameters"]
        present = bool(items)
        if present and expectation.get("expected_json_file"):
            actual = json.loads(
                query(["ssm", "get-parameter", "--name", identifier])["Parameter"]["Value"]
            )
            expected = json.loads(Path(expectation["expected_json_file"]).read_text())
            if actual != expected:
                return False
        if present and expectation.get("required_keys"):
            actual = json.loads(
                query(["ssm", "get-parameter", "--name", identifier])["Parameter"]["Value"]
            )
            if not all(key in actual for key in expectation["required_keys"]):
                return False
    else:
        raise ValueError("Unsupported check type; use instance/volume/snapshot/image/ssm")
    return present == (expectation["expected"] == "present")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expectations", required=True)
    args = parser.parse_args()
    expectations = json.loads(Path(args.expectations).read_text())
    if not isinstance(expectations, list) or not expectations:
        raise ValueError("Provide non-empty exact resource expectations")
    subprocess.run(["bash", str(ROOT / "scripts/preflight.sh")], check=True)
    passed = True
    for item in expectations:
        ok = check(item)
        print(
            json.dumps(
                {"type": item["type"], "id": item["id"], "expected": item["expected"], "passed": ok}
            )
        )
        passed &= ok
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError):
        print(
            "Postflight failed; check permissions, target and expectation structure. AWS values withheld.",
            file=sys.stderr,
        )
        sys.exit(1)
