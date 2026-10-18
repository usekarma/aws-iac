#!/usr/bin/env python3
"""Offline exact-plan provider-read seal; no AWS, apply or plan generation."""

import argparse
import json
import os
from pathlib import Path
import re
import zipfile

import plan_iot_config_read as owner_contract
from seal_m1_discovery import digest, load, rendered_plan

ROOT = Path(__file__).resolve().parents[1]
OWNER = owner_contract.OWNER
REVIEW = Path(
    "/home/ted/dev/iot-digital-twin/artifacts/m1-operator-readiness/m1-provider-read-plan-m9ieoiw4"
)
BASE = ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-discovery.json"
CANDIDATE = ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-provider-read.json"
RECEIPT = OWNER / "maintenance-reviews/m1-discovery-1dhfxzlv/m1-apply-receipt.json"
PINS = {
    "review.tfplan": "f10b2dbdd9229073780b83f66a5b00b5e3f41f9b33dfcd5530bdf7a891e91cb4",
    "plan.json": "670f5fb26f51f35852bda7195f6b14e28d8382af3b4a4f097733e2813987df69",
    "preflight.json": "edb2c2a21d003851b933aaf394acb0a62e3f0760c2a28f40120ed518edfeb97a",
    "result.json": "9c4c5094548c607a2cfab90bfc8201a3655b60c54743db3574a54520f0ec6ebd",
}
BASE_HASH = "ff38cab5e8bcf9fd305d3928f54a7d142a2b64d641bb900a3941bc75fc04b62d"
CANDIDATE_HASH = "5abe14c50e3aa77675a9a06b29e6a924fc96a8e08b13461ceb661ff824a72d30"
RECEIPT_HASH = "95470fcdd31bb3e70f31a4071e6d2ec9f436a1bd79f9801b464bc0e363ef419d"
STATE_HASH = "352ecfe3b3fcbdf1d5a75446171d449aded3ba2849cd0a550922f0c877f3027e"
LINEAGE = "adda9261-8df8-2be4-51cf-f829529878b3"
COMMIT = "d66cbef560058a1bc55000b2a325294d631c329e"
ACCOUNTS = ["623155450153", "835990279085"]
OVERLAY = "artifact_publisher_additions.tf"
OWNER_NAMES = {
    "header.tf",
    "main.tf",
    "outputs.tf",
    "bootstrap_override.tf",
    "terraform.tfstate",
    ".terraform.lock.hcl",
    "bootstrap.tfvars.json",
    ".terraform/terraform.tfstate",
}
ADDITION = {
    "Sid": "M1CloudControlProviderReads",
    "Effect": "Allow",
    "Action": [
        "iam:GetRole",
        "iam:ListRolePolicies",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
    ],
    "Resource": "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control",
    "Condition": {"StringEquals": {"aws:PrincipalAccount": "623155450153"}},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def declarations():
    require(
        digest(BASE) == BASE_HASH and digest(CANDIDATE) == CANDIDATE_HASH,
        "Declaration hash mismatch",
    )
    old, new = load(BASE), load(CANDIDATE)
    expected = json.loads(json.dumps(old))
    require(len(expected["inline_policy"]["Statement"]) == 18, "18-statement baseline required")
    expected["inline_policy"]["Statement"].append(ADDITION)
    require(expected == new, "Only exact four read actions allowed; owner/assignments unchanged")
    return old, new


def validate(owner, review, approval_file):
    require(owner == OWNER and review == REVIEW, "Wrong authoritative owner or review directory")
    require(not owner.is_symlink() and not review.is_symlink(), "Unsafe directory")
    for name, value in PINS.items():
        require(digest(review / name) == value, "Evidence hash mismatch: " + name)
    old, new = declarations()
    state = load(owner / "terraform.tfstate")
    require(
        digest(owner / "terraform.tfstate") == STATE_HASH
        and state["serial"] == 17
        and state["lineage"] == LINEAGE,
        "Stale owner state",
    )
    preflight = load(review / "preflight.json")
    require(
        preflight["serial"] == 17
        and preflight["lineage"] == LINEAGE
        and preflight["baseline_policy_statements"] == 18
        and preflight["source_commit"] == COMMIT,
        "Owner/context evidence mismatch",
    )
    identity = preflight["identity"]
    require(
        identity["Account"] == "835990279085"
        and re.fullmatch(
            r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b/.+",
            identity["Arn"],
        ),
        "Wrong recorded planner identity",
    )
    hashes = preflight["owner_hashes"]
    require(set(hashes) == {str(owner / n) for n in OWNER_NAMES}, "Incomplete owner evidence")
    for name, value in hashes.items():
        require(digest(Path(name)) == value, "Owner integrity mismatch")
    require(
        load(owner / ".terraform/terraform.tfstate")["backend"]
        == {"type": "local", "config": {"path": None, "workspace_dir": None}, "hash": 666019178},
        "Backend mismatch",
    )
    require(
        not (owner / ".terraform/environment").exists() and not (owner / OVERLAY).exists(),
        "Workspace/overlay mismatch",
    )
    require(digest(RECEIPT) == RECEIPT_HASH, "Verified receipt hash mismatch")
    receipt = load(RECEIPT)
    require(
        receipt["status"] == "verified"
        and receipt["postflight"]
        == {
            "status": "verified",
            "serial": 17,
            "lineage": LINEAGE,
            "state_sha256": STATE_HASH,
            "reprovisioning_accounts": ACCOUNTS,
        },
        "Applied owner provenance mismatch",
    )
    plan = load(review / "plan.json")
    managed = {}
    for resource in state["resources"]:
        if resource.get("mode") != "managed":
            continue
        for instance in resource["instances"]:
            address = resource["type"] + "." + resource["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"]) + "]"
            require(address not in managed, "Duplicate state address")
            managed[address] = instance["attributes"]
    owner_contract.validate_plan(plan, managed, old, new)
    variables = load(owner / "bootstrap.tfvars.json")
    variables["bootstrap_config_json"] = json.dumps(new)
    require(
        load(review / "maintenance.tfvars.json") == variables
        and all(plan["variables"][k]["value"] == v for k, v in variables.items()),
        "Plan inputs mismatch",
    )
    require(load(review / "rollback-declaration.json") == old, "Rollback must be verified baseline")
    with zipfile.ZipFile(review / "review.tfplan") as archive:
        sources = {"tfconfig/m-/" + p.name: p.read_bytes() for p in owner.glob("*.tf")}
        sources["tfconfig/m-/" + OVERLAY] = (
            owner / "maintenance-reviews/artifact-publisher-hrrbk83v" / OVERLAY
        ).read_bytes()
        names = archive.namelist()
        require(
            len(names) == len(set(names))
            and {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            == set(sources)
            and all(archive.read(n) == b for n, b in sources.items()),
            "Binary source mismatch",
        )
        require(
            archive.read(".terraform.lock.hcl") == (owner / ".terraform.lock.hcl").read_bytes(),
            "Provider lock mismatch",
        )
        for name in ("tfstate", "tfstate-prev"):
            archived = load_managed(json.loads(archive.read(name)))
            require(archived == load_managed(state), "Binary managed state mismatch")
    require(rendered_plan(owner, review / "review.tfplan") == plan, "Binary/JSON mismatch")
    approval = load(approval_file)
    require(
        approval
        == {
            "schema_version": 1,
            "operation": "m1-provider-read-seal-only",
            "plan_sha256": PINS["review.tfplan"],
            "state_sha256": STATE_HASH,
            "workflow_sha256": digest(Path(__file__)),
            "eventual_reprovisioning_accounts": ACCOUNTS,
            "reprovisioning_impact_acknowledged": True,
            "seal_only_approved": True,
            "apply_approved": False,
        },
        "Separate human seal-only approval/two-account acknowledgment required",
    )
    files = set(PINS) | {"maintenance.tfvars.json", "rollback-declaration.json", "terraform.log"}
    return {
        "schema_version": 1,
        "contract": "m1-provider-read-seal-only-v1",
        "owner_directory": str(owner),
        "review_directory": str(review),
        "plan_sha256": PINS["review.tfplan"],
        "owner_files": hashes
        | {
            str(RECEIPT): digest(RECEIPT),
            str(owner / "maintenance-reviews/artifact-publisher-hrrbk83v" / OVERLAY): digest(
                owner / "maintenance-reviews/artifact-publisher-hrrbk83v" / OVERLAY
            ),
        },
        "review_files": {n: digest(review / n) for n in sorted(files)},
        "approval_file": str(approval_file),
        "approval_sha256": digest(approval_file),
        "repository_inputs": {
            str(p.relative_to(ROOT)): digest(p)
            for p in (
                BASE,
                CANDIDATE,
                Path(__file__),
                ROOT / "scripts/plan_iot_config_read.py",
                ROOT / "scripts/seal_m1_discovery.py",
            )
        },
        "eventual_reprovisioning_accounts": ACCOUNTS,
        "apply_authorized": False,
    }


def load_managed(state):
    return [r for r in state["resources"] if r.get("mode") == "managed"]


def seal(owner, review, approval_file):
    path = review / "m1-provider-read-manifest.json"
    require(not path.exists() and not path.is_symlink(), "Never overwrite/reseal")
    manifest = validate(owner, review, approval_file)
    os.umask(0o077)
    with path.open("x") as output:
        output.write(json.dumps(manifest, indent=2) + "\n")
    path.chmod(0o400)
    print("STOP_FOR_HUMAN: sealed only; apply is unsupported", path, digest(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "seal"])
    parser.add_argument("--owner-dir", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--approval-file", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        validate(args.owner_dir, args.review_dir, args.approval_file)
        print("Verified; no manifest written")
    else:
        seal(args.owner_dir, args.review_dir, args.approval_file)


if __name__ == "__main__":
    main()
