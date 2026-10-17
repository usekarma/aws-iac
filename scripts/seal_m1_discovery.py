#!/usr/bin/env python3
"""Offline M1-only maintenance seal. No apply, AWS calls, or plan generation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

import review_m1_discovery_plan as contract

PLAN_HASH = "6b4420f0fd9c9c1c5f44fe4dae0264c1fd21935591d469b3f9a16804856ef34d"
STATE_HASH = "5b25cc02532bc9c1d42aa89ab7eff4f75d4689f6ea599bc933611fedd7780571"
DELTA_HASH = "e751d189097dd5687bdc7a2db94219bf4760c4dd60a03c8b539ceaef4a90cd91"
CANDIDATE_HASH = "ff38cab5e8bcf9fd305d3928f54a7d142a2b64d641bb900a3941bc75fc04b62d"
ACCOUNTS = ["623155450153", "835990279085"]
OWNER = Path("/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8")
PRIOR = "maintenance-reviews/iot-config-read-6zmoojc2"
OVERLAY = "artifact_publisher_additions.tf"


def digest(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing or unsafe evidence: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    digest(path)
    return json.loads(path.read_text())


def rendered_plan(owner, path):
    env = dict(os.environ, AWS_EC2_METADATA_DISABLED="true", AGENT_MODE="1")
    for key in list(env):
        if key.startswith("TF_CLI_ARGS") or key in {"TF_CLI_CONFIG_FILE", "TF_DATA_DIR"}:
            del env[key]
    result = subprocess.run(
        ["terraform", "show", "-json", str(path)],
        cwd=owner,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def validate(owner, review):
    if owner != OWNER or review.parent != owner / "maintenance-reviews":
        raise ValueError("Use only the existing owner/review directory")
    plan_path = review / "review.tfplan"
    if digest(plan_path) != PLAN_HASH:
        raise ValueError("Approved saved-plan hash mismatch")
    if digest(contract.DELTA) != DELTA_HASH or digest(contract.CANDIDATE) != CANDIDATE_HASH:
        raise ValueError("Exactly seven approved read-only additions required")
    old, new = contract.declarations()
    if len(new["inline_policy"]["Statement"]) - len(old["inline_policy"]["Statement"]) != 7:
        raise ValueError("Seven additions required")
    evidence = load(review / "evidence.json")
    context = load(review / "context.json")
    owner_record = load(review / "owner.json")
    state = load(owner / "terraform.tfstate")
    if digest(owner / "terraform.tfstate") != STATE_HASH or state["serial"] != 15:
        raise ValueError("Owner state mismatch")
    lineage = "adda9261-8df8-2be4-51cf-f829529878b3"
    if state["lineage"] != lineage:
        raise ValueError("Owner lineage mismatch")
    if owner_record != {
        "owner_directory": str(owner),
        "lineage": lineage,
        "serial": 15,
        "state_sha256": STATE_HASH,
        "verified_evidence_sha256": digest(review / "evidence.json"),
    }:
        raise ValueError("Owner evidence mismatch")
    if context != {
        "schema_version": 1,
        "operation": "m1-discovery-seal-only",
        "owner_account": "835990279085",
        "grant_account": "623155450153",
        "region": "us-east-1",
        "plan_sha256": PLAN_HASH,
        "eventual_reprovisioning_accounts": ACCOUNTS,
        "reprovisioning_impact_acknowledged": True,
        "seal_only_approved": True,
        "apply_approved": False,
    }:
        raise ValueError("Explicit seal-only/two-account acknowledgment missing or mismatched")
    identity = evidence["identity"]
    if identity["Account"] != "835990279085" or not re.fullmatch(
        r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b/.+",
        identity["Arn"],
    ):
        raise ValueError("Recorded planning identity differs")
    if (
        evidence["status"] != "STOP_FOR_HUMAN"
        or evidence["sealed"] is not False
        or evidence["apply_authorized"] is not False
        or evidence["plan_sha256"] != PLAN_HASH
        or evidence["reprovisioning_accounts"] != ACCOUNTS
        or evidence["commit"] != "4954eed2eb6904260b08e8ecf73f5ec50ff5dc45"
        or evidence["plan_json_sha256"] != digest(review / "plan.json")
    ):
        raise ValueError("Planning evidence mismatch")
    expected_files = {
        owner / name
        for name in [
            "header.tf",
            "main.tf",
            "outputs.tf",
            "bootstrap_override.tf",
            "terraform.tfstate",
            ".terraform/terraform.tfstate",
            ".terraform.lock.hcl",
            "bootstrap.tfvars.json",
        ]
    }
    if set(evidence["owner_hashes"]) != {str(p) for p in expected_files}:
        raise ValueError("Incomplete owner inventory")
    for name, value in evidence["owner_hashes"].items():
        if digest(Path(name)) != value:
            raise ValueError("Owner integrity mismatch")
    if (
        load(owner / ".terraform/terraform.tfstate")["backend"]
        != {
            "type": "local",
            "config": {"path": None, "workspace_dir": None},
            "hash": 666019178,
        }
        or (owner / ".terraform/environment").exists()
        or (owner / OVERLAY).exists()
    ):
        raise ValueError("Backend/workspace/source mismatch")
    receipt = load(owner / PRIOR / "post-apply.json")
    if receipt["status"] != "verified" or receipt["state_sha256"] != STATE_HASH:
        raise ValueError("Applied provenance mismatch")
    with zipfile.ZipFile(plan_path) as archive:
        names = archive.namelist()
        sources = {"tfconfig/m-/" + p.name: p.read_bytes() for p in owner.glob("*.tf")}
        sources["tfconfig/m-/" + OVERLAY] = (owner / PRIOR / OVERLAY).read_bytes()
        if (
            len(names) != len(set(names))
            or {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            != set(sources)
            or any(archive.read(n) != b for n, b in sources.items())
        ):
            raise ValueError("Saved-plan source provenance mismatch")
        if archive.read(".terraform.lock.hcl") != (owner / ".terraform.lock.hcl").read_bytes():
            raise ValueError("Provider lock mismatch")
        previous = json.loads(archive.read("tfstate-prev"))

        def managed(s):
            return [r for r in s["resources"] if r["mode"] == "managed"]

        if managed(previous) != managed(state):
            raise ValueError("Archived state mismatch")
    plan = load(review / "plan.json")
    if rendered_plan(owner, plan_path) != plan:
        raise ValueError("Binary plan/JSON mismatch")
    contract.review(plan, state)
    variables = load(owner / "bootstrap.tfvars.json")
    variables["bootstrap_config_json"] = json.dumps(new)
    if (
        load(review / "maintenance.tfvars.json") != variables
        or any(plan["variables"][k]["value"] != v for k, v in variables.items())
        or load(review / "rollback-declaration.json") != old
    ):
        raise ValueError("Input/rollback evidence mismatch")
    review_files = {
        name: digest(review / name)
        for name in [
            "review.tfplan",
            "plan.json",
            "evidence.json",
            "context.json",
            "owner.json",
            "maintenance.tfvars.json",
            "rollback-declaration.json",
            "terraform.log",
        ]
    }
    return {
        "schema_version": 1,
        "contract": "m1-discovery-seal-only-v1",
        "owner_directory": str(owner),
        "review_directory": str(review),
        "plan_sha256": PLAN_HASH,
        "owner_files": evidence["owner_hashes"],
        "review_files": review_files,
        "eventual_reprovisioning_accounts": ACCOUNTS,
        "apply_authorized": False,
        "repository_inputs": {
            str(p.relative_to(contract.ROOT)): digest(p)
            for p in [
                contract.BASE,
                contract.CANDIDATE,
                contract.DELTA,
                Path(__file__),
                contract.ROOT / "scripts/review_m1_discovery_plan.py",
                contract.ROOT / "scripts/plan_iot_config_read.py",
            ]
        },
    }


def seal(owner, review):
    manifest = validate(owner, review)
    path = review / "m1-maintenance-manifest.json"
    os.umask(0o077)
    with path.open("x") as output:
        output.write(json.dumps(manifest, indent=2) + "\n")
    path.chmod(0o400)
    print("STOP_FOR_HUMAN: sealed only; separate apply approval required")
    print(path, digest(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "seal"])
    parser.add_argument("--owner-dir", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        validate(args.owner_dir, args.review_dir)
        print("Verified; no manifest written")
    else:
        seal(args.owner_dir, args.review_dir)


if __name__ == "__main__":
    main()
