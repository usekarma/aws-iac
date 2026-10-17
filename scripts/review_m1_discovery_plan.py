#!/usr/bin/env python3
"""Offline review of an existing-owner M1 maintenance plan. Never calls AWS/Terraform."""

import argparse
import json
from pathlib import Path

import plan_iot_config_read as owner

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples/identity-center-owner.iac-plan-readonly.iot-config-read.json"
CANDIDATE = ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-discovery.json"
DELTA = ROOT / "proposals/m1-read-discovery/discovery-policy.json"


def declarations():
    old = json.loads(BASE.read_text())
    new = json.loads(CANDIDATE.read_text())
    delta = json.loads(DELTA.read_text())
    expected = json.loads(BASE.read_text())
    existing = {s["Sid"] for s in old["inline_policy"]["Statement"]}
    additions = delta["Statement"]
    if len({s["Sid"] for s in additions}) != len(additions) or any(
        s["Sid"] in existing for s in additions
    ):
        raise ValueError("Duplicate or conflicting policy statement IDs")
    expected["inline_policy"]["Statement"].extend(additions)
    if expected != new:
        raise ValueError("Candidate must preserve every existing declaration field and permission")
    return old, new


def review(plan, state):
    old, new = declarations()
    if state.get("version") != 4 or not state.get("lineage"):
        raise ValueError("Require the current authoritative owner state")
    managed = {}
    for resource in state["resources"]:
        if resource.get("mode") != "managed":
            continue
        for instance in resource["instances"]:
            address = resource["type"] + "." + resource["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"]) + "]"
            if resource.get("module"):
                address = resource["module"] + "." + address
            if address in managed:
                raise ValueError("Duplicate state resource")
            managed[address] = instance["attributes"]
    if set(managed) != owner.EXPECTED:
        raise ValueError("Unexpected owner resources; no competing owner/import/repair")
    owner.validate_plan(plan, managed, old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--owner-state", type=Path, required=True)
    args = parser.parse_args()
    review(json.loads(args.plan_json.read_text()), json.loads(args.owner_state.read_text()))
    print("STOP_FOR_HUMAN: one inline-policy update, six no-ops; not sealed or authorized")


if __name__ == "__main__":
    main()
