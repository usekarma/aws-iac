#!/usr/bin/env python3
"""Generate private, value-free review evidence from Terraform show -json output."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PERSISTENT = {
    "aws_ebs_volume",
    "aws_ebs_snapshot",
    "aws_ami",
    "aws_ami_from_instance",
    "aws_s3_bucket",
    "aws_s3_object",
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_dynamodb_table",
    "aws_efs_file_system",
    "aws_fsx_lustre_file_system",
    "aws_opensearch_domain",
    "aws_elasticache_replication_group",
}
NETWORK = (
    "aws_security_group",
    "aws_vpc_security_group",
    "aws_network_acl",
    "aws_route",
    "aws_lb",
    "aws_vpc",
    "aws_subnet",
)
ALLOWED = {
    ("no-op",),
    ("create",),
    ("read",),
    ("update",),
    ("delete",),
    ("delete", "create"),
    ("create", "delete"),
    ("forget",),
    ("create", "forget"),
}
CONTEXT = (
    "objective",
    "repositories",
    "files",
    "account",
    "profile",
    "region",
    "environment",
    "binding",
    "prefix",
    "component",
    "nickname",
    "configuration_changes",
    "validation_results",
    "blast_radius",
    "recovery",
    "post_change_checks",
)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("resource_changes"), list):
        raise ValueError(
            "Expected Terraform plan JSON with resource_changes; state JSON is not a plan"
        )
    if not str(plan.get("format_version", "")).startswith("1."):
        raise ValueError("Unsupported Terraform JSON format")
    if plan.get("errored") is True or plan.get("complete") is False:
        raise ValueError("Errored/incomplete plan cannot support deployment review")
    rows = []
    for resource in plan["resource_changes"]:
        change = resource["change"]
        actions = tuple(change["actions"])
        if actions not in ALLOWED:
            raise ValueError("Unsupported Terraform action; review manually")
        kind = resource["type"]
        if not isinstance(kind, str) or not isinstance(resource.get("address"), str):
            raise ValueError("Malformed resource identity")
        if resource.get("mode", "managed") == "data":
            continue
        flags = []
        if "delete" in actions:
            flags.append("resource-deletion")
        if "forget" in actions:
            flags.append("state-forget-resource-may-survive-and-cost-money")
        if kind in PERSISTENT:
            flags.append(
                "persistent-data-review"
                if actions != ("no-op",)
                else "managed-persistent-resource-preserved"
            )
            if "delete" in actions:
                flags.append("potential-irreversible-data-loss")
        if kind == "aws_instance" and "delete" in actions:
            flags.append("instance-root-and-inline-ebs-data-loss-review")
        if actions != ("no-op",):
            if kind.startswith("aws_iam_") or kind.startswith("aws_kms_"):
                flags.append("security-boundary-approval")
            if kind.startswith(NETWORK):
                flags.append("network-boundary-approval")
            if change.get("after_unknown"):
                flags.append("values-unknown-until-apply")
        rows.append(
            {"address": resource["address"], "type": kind, "actions": list(actions), "flags": flags}
        )
    return rows


def generate(plan_path, context_path, output, saved_plan=None):
    context = load(context_path)
    missing = [key for key in CONTEXT if key not in context or context[key] in (None, "", [])]
    if missing:
        raise ValueError("Missing review context: " + ", ".join(missing))
    if not (
        isinstance(context["account"], str)
        and len(context["account"]) == 12
        and context["account"].isdigit()
    ):
        raise ValueError("Account must be an explicit 12-digit string")
    rows = analyze(load(plan_path))
    deleted = any("delete" in row["actions"] for row in rows)
    forgotten = any("forget" in row["actions"] for row in rows)
    evidence = {
        "schema_version": 1,
        "status": "proposal-human-review-required",
        "context": {key: context[key] for key in CONTEXT},
        "source": {
            "plan_json_sha256": digest(plan_path),
            "saved_plan_sha256": digest(saved_plan) if saved_plan else None,
            "binding_verified_by_generator": False,
            "plan_complete": load(plan_path).get("complete"),
            "terraform_version": load(plan_path).get("terraform_version"),
            "synthetic": bool(context.get("synthetic", False)),
        },
        "resources": rows,
        "action_counts": dict(Counter(action for row in rows for action in row["actions"])),
        "drift_resource_count": len(load(plan_path).get("resource_drift", [])),
        "required_approval": "strong-destructive" if deleted or forgotten else "human-execution",
        "limitations": [
            "Target and validation context are supplied by the caller, not independently attested.",
            "Plan JSON is not a complete AWS inventory; unmanaged volumes, AMIs, snapshots and backups may survive and cost money.",
            "No-op resources are preserved only in this plan; resources absent from the plan are unverified.",
            "Regenerate and review after code/config/state/identity changes. No execution authority is granted.",
        ],
    }
    try:
        evidence["repository_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        evidence["repository_commit"] = None
    out = Path(output)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("Use an empty/new private evidence directory")
    os.umask(0o077)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    lines = [
        "# Infrastructure change evidence",
        "",
        "Status: proposal; human review required.",
        "",
        f"Objective: {context['objective']}",
        "",
        f"Target: account {context['account']}, region {context['region']}, environment {context['environment']}, binding {context['binding']}",
        f"Component/nickname: {context['component']}/{context['nickname']}",
        f"Approval: {evidence['required_approval']}",
        "",
        "| Resource | Actions | Review flags |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        # Escape table/newline content from external plan addresses.
        def escape(value):
            return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

        lines.append(
            f"| {escape(row['address'])} | {', '.join(row['actions'])} | {', '.join(row['flags'])} |"
        )
    for key in (
        "files",
        "configuration_changes",
        "validation_results",
        "blast_radius",
        "recovery",
        "post_change_checks",
    ):
        lines += ["", f"## {key.replace('_', ' ').title()}", "", str(context[key])]
    lines += ["", "## Limitations", ""] + ["- " + item for item in evidence["limitations"]]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--saved-plan", help="Exact saved binary plan whose digest the reviewer approves"
    )
    args = parser.parse_args()
    generate(args.plan_json, args.context, args.output, args.saved_plan)
    print("Private evidence generated; no AWS calls, values or Terraform state included.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(
            f"Evidence generation failed: {type(exc).__name__}; check plan/context structure and paths",
            file=sys.stderr,
        )
        sys.exit(1)
