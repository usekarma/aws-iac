#!/usr/bin/env python3
"""Hash-bound recovery seal/apply, fixed policy delta; never generates plans."""

import argparse
import json
import os
import re
from pathlib import Path
import zipfile

import apply_m1_provider_reads as execution
import seal_m1_provider_reads as original
from seal_m1_provider_reads import (
    ACCOUNTS,
    BASE,
    CANDIDATE,
    LINEAGE,
    OVERLAY,
    OWNER,
    OWNER_NAMES,
    declarations,
    digest,
    load,
    load_managed,
    owner_contract,
    rendered_plan,
    require,
)

ROOT = Path(__file__).resolve().parents[1]


def validate_binding(path, owner, review):
    b = load(path)
    require(
        set(b)
        == {
            "schema_version",
            "owner_directory",
            "review_directory",
            "serial",
            "lineage",
            "state_sha256",
            "source_commit",
            "review_hashes",
            "recovery_hashes",
            "raw_directory",
            "prior_review",
            "prior_manifest_name",
        },
        "Binding schema mismatch",
    )
    require(
        b["schema_version"] == 1
        and b["owner_directory"] == str(OWNER)
        and owner == OWNER
        and b["review_directory"] == str(review)
        and review != original.REVIEW
        and b["lineage"] == LINEAGE
        and type(b["serial"]) is int
        and b["serial"] >= 18,
        "Recovery owner/serial mismatch",
    )
    require(set(b["review_hashes"]) == set(original.PINS), "Complete new plan evidence required")
    require(
        b["review_hashes"]["review.tfplan"] != original.PINS["review.tfplan"],
        "Never reuse original plan",
    )
    require(review.resolve() == review and owner.resolve() == owner, "Unsafe directory")
    for name, value in b["recovery_hashes"].items():
        require(digest(Path(name)) == value, "Recovery evidence tampered")
    return b


def require_recovery(b):
    raw = Path(b["raw_directory"])
    prior = Path(b["prior_review"])
    require(
        b["prior_manifest_name"]
        in {"m1-provider-read-manifest.json", "m1-provider-read-recovery-manifest.json"},
        "Unsupported prior manifest",
    )
    prior_manifest = prior / b["prior_manifest_name"]
    inventory = load(raw / "capture-hashes.json")
    required = {"owner-sts.json", "target-sts.json", "central-inline.json", "provisioned.json"}
    for account in ACCOUNTS:
        required |= {
            account + "-" + suffix + ".json"
            for suffix in ("assignments", "role", "inline-names", "managed", "inline")
        }
    require(set(inventory) == required, "Complete 14-file recovery capture required")
    required_paths = {raw / n for n in required | {"capture-hashes.json"}} | {
        prior / "m1-provider-read-apply-receipt.json",
        prior / "plan.json",
        prior / "review.tfplan",
        prior_manifest,
    }
    require(
        set(b["recovery_hashes"]) == {str(p) for p in required_paths},
        "Recovery provenance inventory mismatch",
    )
    for name, value in inventory.items():
        require(digest(raw / name) == value, "Raw capture hash mismatch")
    old, new = declarations()
    require(
        json.loads(load(raw / "central-inline.json")["InlinePolicy"]) == old["inline_policy"],
        "Central recovery policy mismatch",
    )
    require(
        set(load(raw / "provisioned.json")["AccountIds"]) == set(ACCOUNTS),
        "Both accounts must be latest-provisioned",
    )
    for account in ACCOUNTS:
        role = load(raw / (account + "-role.json"))["Role"]
        expected_role = execution.ROLES[account]
        require(
            role["Arn"]
            == "arn:aws:iam::" + account + ":role/aws-reserved/sso.amazonaws.com/" + expected_role
            and not role.get("PermissionsBoundary"),
            "Recovery role/boundary mismatch",
        )
        require(
            load(raw / (account + "-inline-names.json"))["PolicyNames"] == ["AwsSSOInlinePolicy"]
            and load(raw / (account + "-managed.json"))["AttachedPolicies"] == [],
            "Recovery attachments mismatch",
        )
        document = load(raw / (account + "-inline.json"))
        require(
            document["RoleName"] == expected_role
            and document["PolicyName"] == "AwsSSOInlinePolicy"
            and document["PolicyDocument"] == old["inline_policy"],
            "Recovery policy mismatch",
        )
        assignments = load(raw / (account + "-assignments.json"))["AccountAssignments"]
        require(
            assignments
            == [
                {
                    "AccountId": account,
                    "PermissionSetArn": execution.PS,
                    "PrincipalType": "USER",
                    "PrincipalId": owner_contract.PRINCIPAL,
                }
            ],
            "Recovery assignment mismatch",
        )
    for filename, account in [
        ("owner-sts.json", "835990279085"),
        ("target-sts.json", "623155450153"),
    ]:
        identity = load(raw / filename)
        require(
            identity["Account"] == account
            and identity["Arn"].startswith("arn:aws:sts::" + account + ":assumed-role/"),
            "Recovery capture identity mismatch",
        )
    failed = load(prior / "m1-provider-read-apply-receipt.json")
    manifest = load(prior_manifest)
    require(
        failed["status"] == "failed-stop-for-human"
        and failed["terraform_exit_code"] != 0
        and failed["manifest_sha256"] == digest(prior_manifest)
        and failed["plan_sha256"] == digest(prior / "review.tfplan")
        and manifest["plan_sha256"] == failed["plan_sha256"]
        and manifest["review_files"]["plan.json"] == digest(prior / "plan.json"),
        "Prior failed-attempt provenance mismatch",
    )
    require(
        b["review_hashes"]["review.tfplan"] != digest(prior / "review.tfplan"),
        "Never reuse failed plan",
    )
    require(
        manifest["owner_directory"] == str(OWNER) and manifest["review_directory"] == str(prior),
        "Failed manifest owner mismatch",
    )
    plan = load(prior / "plan.json")
    state = load(OWNER / "terraform.tfstate")
    managed = managed_state(state)
    owner_contract.validate_plan(plan, managed, old, new)
    # Existing failed attempt must not have changed the seven managed resources.
    require(
        state["lineage"] == LINEAGE and state["serial"] == b["serial"], "Recovery state mismatch"
    )


def managed_state(state):
    result = {}
    for r in state["resources"]:
        if r.get("mode") != "managed":
            continue
        for i in r["instances"]:
            n = r["type"] + "." + r["name"]
            if "index_key" in i:
                n += "[" + json.dumps(i["index_key"]) + "]"
            require(not r.get("module") and n not in result, "Unexpected state address")
            result[n] = i["attributes"]
    return result


def validate(owner, review, approval_file, binding_file):
    binding = validate_binding(binding_file, owner, review)
    PINS = binding["review_hashes"]
    STATE_HASH = binding["state_sha256"]
    COMMIT = binding["source_commit"]
    REVIEW = review
    serial = binding["serial"]
    require_recovery(binding)
    require(owner == OWNER and review == REVIEW, "Wrong authoritative owner or review directory")
    require(not owner.is_symlink() and not review.is_symlink(), "Unsafe directory")
    for name, value in PINS.items():
        require(digest(review / name) == value, "Evidence hash mismatch: " + name)
    old, new = declarations()
    state = load(owner / "terraform.tfstate")
    require(
        digest(owner / "terraform.tfstate") == STATE_HASH
        and state["serial"] == serial
        and state["lineage"] == LINEAGE,
        "Stale owner state",
    )
    preflight = load(review / "preflight.json")
    require(
        preflight["serial"] == serial
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
        saved_state = json.loads(archive.read("tfstate"))
        require(
            saved_state["serial"] == serial and saved_state["lineage"] == LINEAGE,
            "Saved plan state metadata mismatch",
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
            "operation": "m1-provider-read-recovery-seal-only",
            "plan_sha256": PINS["review.tfplan"],
            "state_sha256": STATE_HASH,
            "binding_sha256": digest(binding_file),
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
        "contract": "m1-provider-read-recovery-v1",
        "owner_directory": str(owner),
        "review_directory": str(review),
        "plan_sha256": PINS["review.tfplan"],
        "owner_files": hashes
        | {
            str(owner / "maintenance-reviews/artifact-publisher-hrrbk83v" / OVERLAY): digest(
                owner / "maintenance-reviews/artifact-publisher-hrrbk83v" / OVERLAY
            ),
        },
        "review_files": {n: digest(review / n) for n in sorted(files)},
        "binding_file": str(binding_file),
        "binding_sha256": digest(binding_file),
        "serial": serial,
        "recovery_hashes": binding["recovery_hashes"],
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
                ROOT / "scripts/seal_m1_provider_reads.py",
                ROOT / "scripts/apply_m1_provider_reads.py",
            )
        },
        "eventual_reprovisioning_accounts": ACCOUNTS,
        "apply_authorized": False,
    }


def seal(owner, review, approval_file, binding_file):
    path = review / "m1-provider-read-recovery-manifest.json"
    require(not path.exists() and not path.is_symlink(), "Never overwrite recovery seal")
    manifest = validate(owner, review, approval_file, binding_file)
    os.umask(0o077)
    with path.open("x") as f:
        f.write(json.dumps(manifest, indent=2) + "\n")
    path.chmod(0o400)
    print("Sealed only; apply remains unauthorized", path, digest(path))


def execution_manifest(owner, review, binding_file, expected_hash, after=False):
    path = review / "m1-provider-read-recovery-manifest.json"
    require(digest(path) == expected_hash, "Recovery manifest hash mismatch")
    m = load(path)
    require(
        m["contract"] == "m1-provider-read-recovery-v1"
        and m["apply_authorized"] is False
        and m["owner_directory"] == str(OWNER)
        and owner == OWNER
        and m["review_directory"] == str(review)
        and m["binding_file"] == str(binding_file)
        and m["binding_sha256"] == digest(binding_file),
        "Recovery sealed context mismatch",
    )
    for n, h in m["review_files"].items():
        require(digest(review / n) == h, "Recovery review tampered")
    for n, h in m["owner_files"].items():
        if after and Path(n) == owner / "terraform.tfstate":
            continue
        require(digest(Path(n)) == h, "Recovery owner tampered")
    for n, h in m["repository_inputs"].items():
        require(digest(ROOT / n) == h, "Recovery source tampered")
    for n, h in m["recovery_hashes"].items():
        require(digest(Path(n)) == h, "Recovery record tampered")
    require(digest(Path(m["approval_file"])) == m["approval_sha256"], "Seal approval tampered")
    return m


def execute(action, owner, review, approval_file, binding_file):
    require(action in {"preflight", "apply"}, "Recovery action mismatch")
    env = execution.environment(action)
    approved = load(approval_file)
    require(
        set(approved)
        == {
            "operation",
            "approved",
            "workflow_sha256",
            "plan_sha256",
            "manifest_sha256",
            "binding_sha256",
            "reprovisioning_accounts",
            "reprovisioning_impact_acknowledged",
            "owner_profile",
            "owner_identity_arn",
            "target_read_profile",
            "target_read_identity_arn",
        },
        "Recovery approval schema mismatch",
    )
    binding = load(binding_file)
    require(
        approved["operation"] == "m1-provider-read-recovery-apply"
        and approved["workflow_sha256"] == digest(Path(__file__))
        and approved["binding_sha256"] == digest(binding_file)
        and approved["plan_sha256"] == binding["review_hashes"]["review.tfplan"]
        and approved["reprovisioning_accounts"] == ACCOUNTS
        and approved["owner_profile"] == "identity-center-admin"
        and re.fullmatch(
            r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_[0-9a-f]+/.+",
            approved["owner_identity_arn"],
        )
        and (
            approved["approved"] is True
            or (action == "preflight" and approved["approved"] is False)
        )
        and (action == "preflight" or approved["reprovisioning_impact_acknowledged"] is True),
        "Separate exact recovery execution approval required",
    )
    m = execution_manifest(owner, review, binding_file, approved["manifest_sha256"])
    validate(owner, review, Path(m["approval_file"]), binding_file)
    execution.guard_identity(
        env, approved["owner_profile"], approved["owner_identity_arn"], "835990279085"
    )
    execution.verify_live(env, approved, declarations()[0])
    if action == "preflight":
        print("Read-only recovery preflight passed; no approval inferred")
        return
    execution_manifest(owner, review, binding_file, approved["manifest_sha256"])
    path = review / "m1-provider-read-apply-receipt.json"
    os.umask(0o077)
    receipt = {
        "status": "attempt-started",
        "approval_sha256": digest(approval_file),
        "manifest_sha256": approved["manifest_sha256"],
        "plan_sha256": approved["plan_sha256"],
        "operator_arn": approved["owner_identity_arn"],
        "terraform_exit_code": None,
    }
    with path.open("x") as f:
        f.write(json.dumps(receipt, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        with (review / "m1-provider-read-apply.log").open("x") as log:
            result = execution.subprocess.run(
                ["terraform", "apply", "-input=false", "-no-color", str(review / "review.tfplan")],
                cwd=owner,
                env=dict(env, AWS_PROFILE=approved["owner_profile"]),
                stdout=log,
                stderr=execution.subprocess.STDOUT,
                timeout=1800,
                check=False,
            )
        receipt["terraform_exit_code"] = result.returncode
        require(result.returncode == 0, "Recovery apply failed; no retry/rollback")
        execution_manifest(owner, review, binding_file, approved["manifest_sha256"], after=True)
        state = execution.state_after(owner, review)
        require(state["serial"] > binding["serial"], "Recovery serial did not advance")
        execution.verify_live(env, approved)
        receipt["postflight"] = {
            "status": "verified",
            "serial": state["serial"],
            "lineage": state["lineage"],
            "state_sha256": digest(owner / "terraform.tfstate"),
            "reprovisioning_accounts": ACCOUNTS,
        }
        receipt["status"] = "verified"
    except Exception as exc:
        receipt.update(status="failed-stop-for-human", failure_type=type(exc).__name__)
        raise
    finally:
        path.write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "seal", "preflight", "apply"])
    for name in ("owner-dir", "review-dir", "approval-file", "binding-file"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    if a.action == "verify":
        validate(a.owner_dir, a.review_dir, a.approval_file, a.binding_file)
        print("Verified only; no seal written")
    elif a.action == "seal":
        seal(a.owner_dir, a.review_dir, a.approval_file, a.binding_file)
    else:
        execute(a.action, a.owner_dir, a.review_dir, a.approval_file, a.binding_file)


if __name__ == "__main__":
    main()
