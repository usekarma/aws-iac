#!/usr/bin/env python3
"""Classify private read-only inventory. Candidates never imply deletion authority."""

import json
from pathlib import Path
import sys


def classify(inventory):
    report = {"authority": "inspection-only-no-deletion-approval", "candidates": []}
    for volume in inventory["volumes"]:
        if volume["State"] == "available" and not volume.get("Attachments"):
            report["candidates"].append(
                {
                    "type": "detached-volume",
                    "id": volume["Id"],
                    "cost": "storage continues",
                    "verification": "Identify owner/data/backups and restore need before deletion",
                }
            )
    for address in inventory["addresses"]:
        if not address.get("Association"):
            report["candidates"].append(
                {
                    "type": "unassociated-eip",
                    "id": address["Id"],
                    "cost": "public IPv4 charges may continue",
                    "verification": "Verify ownership and pending reuse",
                }
            )
    for kind in ("snapshots", "images", "load-balancers", "nat-gateways"):
        for resource in inventory[kind]:
            if resource.get("State") in ("deleted", "failed"):
                continue
            report["candidates"].append(
                {
                    "type": kind,
                    "id": resource.get("Id", resource.get("Arn")),
                    "cost": "Review ongoing storage/runtime costs",
                    "verification": "Inventory alone cannot establish unused; check references and preservation requirements",
                }
            )
    report["limitations"] = [
        "Selected account/region only; check all relevant regions and accounts",
        "No S3/database/ECS inventory; assess those separately",
        "AMIs may retain multiple snapshots; do not delete a snapshot solely because its source instance is gone",
    ]
    return report


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    inventory = {
        p.stem: json.loads(p.read_text())
        for p in directory.glob("*.json")
        if p.name != "cost-review.json"
    }
    report = classify(inventory)
    (directory / "cost-review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Read-only inventory: {len(report['candidates'])} items require cost/preservation review; none authorized for deletion."
    )
