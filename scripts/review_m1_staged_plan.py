#!/usr/bin/env python3
"""Offline mandatory review gate for same-state M1 stages; no AWS/Terraform calls."""

import argparse
import json
from pathlib import Path

ROLE = {
    "module.cloud_control[0].aws_iam_role.cloud_control",
    "module.cloud_control[0].aws_iam_role_policy.handlers",
}

OPERATIONAL = {
    "module.operational[0]." + address
    for address in [
        "awscc_iotsitewise_asset_model.model",
        "awscc_iotsitewise_asset.asset",
        "awscc_iot_topic_rule.telemetry",
        "aws_iot_thing.producer",
        "aws_iot_policy.producer",
        "aws_cloudwatch_log_group.errors",
        "aws_iam_role.routing",
        "aws_iam_role_policy.routing",
    ]
} | {"aws_ssm_parameter.runtime[0]"}


def review(plan, stage):
    if stage not in {"service-role-bootstrap", "operational"}:
        raise ValueError("Unknown stage")
    if plan.get("complete") is not True or any(
        plan.get(key)
        for key in ("errored", "resource_drift", "deferred_changes", "action_invocations")
    ):
        raise ValueError("Incomplete/drifting plan")
    rows = {
        r["address"]: r
        for r in plan.get("resource_changes", [])
        if r.get("mode", "managed") == "managed"
    }
    managed_rows = [
        r for r in plan.get("resource_changes", []) if r.get("mode", "managed") == "managed"
    ]
    if len(rows) != len(managed_rows):
        raise ValueError("Duplicate managed addresses")
    if stage == "operational" and set(rows) != ROLE | OPERATIONAL | {"terraform_data.mode"}:
        raise ValueError("Stage 2 must contain exactly the approved component addresses")
    if not ROLE <= rows.keys():
        raise ValueError("Both service role addresses must remain in the canonical state")
    for address, row in rows.items():
        change = row["change"]
        if (
            row.get("previous_address")
            or change.get("importing")
            or change.get("replace_paths")
            or "delete" in change["actions"]
        ):
            raise ValueError("No import/move/replacement/deletion")
        if stage == "service-role-bootstrap":
            if address not in ROLE | {"terraform_data.mode"} or change["actions"] not in [
                ["create"],
                ["no-op"],
            ]:
                raise ValueError(
                    "Stage 1 allows only role/policy/local guard; no operational downgrade"
                )
        elif address in ROLE and (
            change["actions"] != ["no-op"] or change["before"] != change["after"]
        ):
            raise ValueError("Stage 2 must retain bootstrap role/policy unchanged")
        elif address not in ROLE and not (
            address == "terraform_data.mode"
            or address == "aws_ssm_parameter.runtime[0]"
            or address.startswith("module.operational[0].")
        ):
            raise ValueError("Unrelated resource in operational plan")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--stage", choices=["service-role-bootstrap", "operational"], required=True)
    args = parser.parse_args()
    review(json.loads(args.plan_json.read_text()), args.stage)
    print("Stage scope validated; human policy/ownership review still required")


if __name__ == "__main__":
    main()
