#!/usr/bin/env python3
"""Exact additive IAM maintenance; never plans, retries, or applies competing state."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import apply_m1_provider_reads as runtime

OWNER = Path("/home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8")
ACCOUNTS = ["623155450153", "835990279085"]
ADDRESS = "aws_ssoadmin_permission_set_inline_policy.inline_policy"


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exclusive(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def validate_plan(plan, baseline, additions):
    require(
        additions and all(s.get("Effect") == "Allow" for s in additions),
        "Explicit allow additions required",
    )
    require(
        len({s["Sid"] for s in baseline["inline_policy"]["Statement"] + additions})
        == len(baseline["inline_policy"]["Statement"]) + len(additions),
        "Duplicate statement SID",
    )
    expected = baseline["inline_policy"] | {
        "Statement": baseline["inline_policy"]["Statement"] + additions
    }
    resources = [r for r in plan["resource_changes"] if r["mode"] == "managed"]
    changed = [r for r in resources if r["change"]["actions"] != ["no-op"]]
    require(
        len(resources) == 7 and len(changed) == 1, "Require one update and six unchanged resources"
    )
    change = changed[0]
    require(
        change["address"] == ADDRESS and change["change"]["actions"] == ["update"],
        "Only inline-policy update allowed",
    )
    before, after = change["change"]["before"], change["change"]["after"]
    require(json.loads(before["inline_policy"]) == baseline["inline_policy"], "Baseline mismatch")
    require(json.loads(after["inline_policy"]) == expected, "Unexpected policy delta")
    require(
        {k: v for k, v in before.items() if k != "inline_policy"}
        == {k: v for k, v in after.items() if k != "inline_policy"},
        "Unexpected resource attribute change",
    )
    require(not plan.get("resource_drift"), "Unreviewed refresh drift")
    require(
        not any(
            r.get("change", {}).get("importing") or r.get("change", {}).get("replace_paths")
            for r in resources
        ),
        "Import/replacement forbidden",
    )
    return baseline | {"inline_policy": expected}


def validate(contract_path, after=False):
    c = load(contract_path)
    require(
        set(c)
        == {
            "contract",
            "owner_directory",
            "review_directory",
            "planning_directory",
            "state_serial",
            "state_lineage",
            "owner_hashes",
            "files",
            "baseline_file",
            "additions",
            "source_files",
            "evidence_files",
            "reprovisioning_accounts",
        },
        "Contract schema mismatch",
    )
    require(c["contract"] == "declarative-iam-maintenance-v1", "Wrong contract")
    owner, review, planning = (
        Path(c[k]) for k in ("owner_directory", "review_directory", "planning_directory")
    )
    require(
        owner == OWNER
        and owner.resolve() == OWNER
        and review.resolve() == review
        and planning.resolve() == planning
        and planning != owner,
        "Wrong canonical owner or unsafe path",
    )
    require(c["reprovisioning_accounts"] == ACCOUNTS, "Both-account acknowledgment required")
    for collection in ("files", "owner_hashes"):
        for name, expected in c[collection].items():
            path = review / name if collection == "files" else owner / name
            root = review if collection == "files" else owner
            require(
                not Path(name).is_absolute()
                and ".." not in Path(name).parts
                and path.resolve().is_relative_to(root),
                "Evidence path escapes root",
            )
            require(not path.is_symlink(), "Symlink evidence forbidden")
            if after and collection == "owner_hashes" and name == "terraform.tfstate":
                continue
            require(digest(path) == expected, "Hash mismatch: " + name)
    require(
        {"review.tfplan", "plan.json", c["baseline_file"]} <= c["files"].keys(),
        "Missing plan/baseline evidence",
    )
    require(
        set(c["evidence_files"]) == {"owner-context.json", "rollback.json"}
        and all(n in c["files"] for n in c["evidence_files"]),
        "Missing structured evidence",
    )
    for name in c["evidence_files"]:
        require(isinstance(load(review / name), dict), "Structured evidence required")
    required_owner = (
        {p.name for p in owner.glob("*.tf")}
        | {p.name for p in owner.glob("*.tf.json")}
        | {
            "terraform.tfstate",
            ".terraform.lock.hcl",
            "bootstrap.tfvars.json",
            ".terraform/terraform.tfstate",
        }
    )
    require(set(c["owner_hashes"]) == required_owner, "Incomplete owner evidence")
    state = load(owner / "terraform.tfstate")
    require(
        state["lineage"] == c["state_lineage"]
        and (
            state["serial"] > c["state_serial"] if after else state["serial"] == c["state_serial"]
        ),
        "Stale owner state",
    )
    require(
        load(owner / ".terraform/terraform.tfstate")["backend"]["type"] == "local",
        "Require existing local backend",
    )
    require(
        load(owner / ".terraform/terraform.tfstate")["backend"]["config"]
        == {"path": None, "workspace_dir": None},
        "Redirected local backend",
    )
    require(not (owner / ".terraform/environment").exists(), "Require default workspace")
    baseline = load(review / c["baseline_file"])
    context = load(review / "owner-context.json")
    require(
        context
        == {
            "owner_directory": str(owner),
            "state_serial": c["state_serial"],
            "state_lineage": c["state_lineage"],
            "owner_hashes": c["owner_hashes"],
            "planning_directory": str(planning),
        },
        "Owner/context evidence mismatch",
    )
    require(
        load(review / "rollback.json")
        == {
            "baseline": baseline,
            "automatic_rollback": False,
            "requires_new_plan_and_human_approval": True,
        },
        "Rollback evidence mismatch",
    )
    require(
        {a["target_account_id"] for a in baseline["assignments"]} == set(ACCOUNTS),
        "Assignment scope mismatch",
    )
    desired = validate_plan(load(review / "plan.json"), baseline, c["additions"])
    with zipfile.ZipFile(review / "review.tfplan") as archive:
        names = {
            n.removeprefix("tfconfig/m-/")
            for n in archive.namelist()
            if n.startswith("tfconfig/m-/") and n.endswith((".tf", ".tf.json"))
        }
        require(names == set(c["source_files"]), "Saved-plan source mismatch")
        for name, expected in c["source_files"].items():
            require(
                "/" not in name
                and hashlib.sha256(archive.read("tfconfig/m-/" + name)).hexdigest() == expected,
                "Source hash mismatch",
            )
            if (owner / name).exists():
                require(digest(owner / name) == expected, "Canonical source differs")
            else:
                require(
                    name in c["files"] and digest(review / name) == expected,
                    "Missing verified execution source",
                )
        require(
            archive.read(".terraform.lock.hcl") == (owner / ".terraform.lock.hcl").read_bytes(),
            "Provider lock mismatch",
        )
    snapshot = load(planning / "terraform.tfstate")

    def managed(value):
        return {
            (r.get("module", ""), r["type"], r["name"], str(i.get("index_key", ""))): i[
                "attributes"
            ]
            for r in value["resources"]
            if r["mode"] == "managed"
            for i in r["instances"]
        }

    original, current = managed(snapshot), managed(state)
    require(
        len(original) == 7 and original.keys() == current.keys(),
        "Managed state resource inventory changed",
    )
    for key, attrs in original.items():
        actual = current[key]
        if after and key[1:3] == ("aws_ssoadmin_permission_set_inline_policy", "inline_policy"):
            require(
                {k: v for k, v in attrs.items() if k != "inline_policy"}
                == {k: v for k, v in actual.items() if k != "inline_policy"},
                "Unexpected state attribute change",
            )
        else:
            require(actual == attrs, "Unrelated state resource changed")
    expected_state = desired if after else baseline
    policy = next(
        r
        for r in state["resources"]
        if r["type"] == "aws_ssoadmin_permission_set_inline_policy" and r["name"] == "inline_policy"
    )["instances"][0]["attributes"]
    require(
        json.loads(policy["inline_policy"]) == expected_state["inline_policy"],
        "Owner policy mismatch",
    )
    # Verify binary/JSON correspondence using the already initialized planning copy.
    require(
        digest(planning / "terraform.tfstate") == c["owner_hashes"]["terraform.tfstate"],
        "Planning copy state differs",
    )
    require(
        {p.name for p in planning.glob("*.tf")} | {p.name for p in planning.glob("*.tf.json")}
        == set(c["source_files"]),
        "Planning source inventory mismatch",
    )
    for name, expected in c["source_files"].items():
        require(digest(planning / name) == expected, "Planning source differs")
    require(
        (planning / ".terraform.lock.hcl").read_bytes()
        == (owner / ".terraform.lock.hcl").read_bytes(),
        "Planning lock mismatch",
    )
    shown = subprocess.run(
        ["terraform", "show", "-json", str(review / "review.tfplan")],
        cwd=planning,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    require(
        json.loads(shown.stdout) == load(review / "plan.json"),
        "Saved plan JSON differs from binary",
    )
    return c, baseline, desired


def approved(path, action, contract_path, manifest=None):
    a = load(path)
    require(
        set(a)
        == {
            "operation",
            "approved",
            "contract_sha256",
            "workflow_sha256",
            "manifest_sha256",
            "reprovisioning_accounts",
            "reprovisioning_impact_acknowledged",
            "owner_profile",
            "owner_identity_arn",
            "target_read_profile",
            "target_read_identity_arn",
        },
        "Approval schema mismatch",
    )
    require(
        a["operation"] == action
        and a["approved"] is True
        and a["contract_sha256"] == digest(contract_path),
        "Separate exact human approval required",
    )
    require(
        a["workflow_sha256"] == workflow_hash()
        and a["reprovisioning_accounts"] == ACCOUNTS
        and a["reprovisioning_impact_acknowledged"] is True,
        "Workflow or reprovisioning acknowledgment mismatch",
    )
    require(
        a["owner_profile"] == "identity-center-admin"
        and a["target_read_profile"] == "m1-dev-operator",
        "Named human profiles required",
    )
    require(
        a["manifest_sha256"] == (digest(manifest) if manifest else None),
        "Manifest approval mismatch",
    )
    return a


def workflow_hash():
    # Imported runtime and its imported validators are executable dependencies.
    paths = sorted(Path(__file__).parent.glob("*.py"))
    return hashlib.sha256("".join(digest(p) for p in paths).encode()).hexdigest()


def live(env, approval, declaration, evidence):
    calls = []

    def aws(profile, *args):
        response = runtime.aws(env, profile, *args)
        calls.append({"profile": profile, "arguments": list(args), "response": response})
        return response

    try:
        for account in ACCOUNTS:
            profile = (
                approval["owner_profile"]
                if account == "835990279085"
                else approval["target_read_profile"]
            )
            expected = (
                approval["owner_identity_arn"]
                if account == "835990279085"
                else approval["target_read_identity_arn"]
            )
            identity = aws(profile, "sts", "get-caller-identity")
            require(
                identity["Account"] == account and identity["Arn"] == expected,
                "Live identity mismatch",
            )
        args = ("--instance-arn", runtime.INSTANCE, "--permission-set-arn", runtime.PS)
        central = aws(
            approval["owner_profile"], "sso-admin", "get-inline-policy-for-permission-set", *args
        )
        require(
            json.loads(central["InlinePolicy"]) == declaration["inline_policy"],
            "Live central policy mismatch",
        )
        accounts = aws(
            approval["owner_profile"],
            "sso-admin",
            "list-accounts-for-provisioned-permission-set",
            *args,
            "--provisioning-status",
            "LATEST_PERMISSION_SET_PROVISIONED",
        )
        require(set(accounts["AccountIds"]) == set(ACCOUNTS), "Both-account provisioning mismatch")
        for account in ACCOUNTS:
            profile = (
                approval["owner_profile"]
                if account == "835990279085"
                else approval["target_read_profile"]
            )
            role = runtime.ROLES[account]
            actual = aws(profile, "iam", "get-role", "--role-name", role)["Role"]
            require(
                actual["Arn"]
                == f"arn:aws:iam::{account}:role/aws-reserved/sso.amazonaws.com/{role}"
                and not actual.get("PermissionsBoundary"),
                "Role identity/boundary mismatch",
            )
            require(
                aws(profile, "iam", "list-role-policies", "--role-name", role)["PolicyNames"]
                == ["AwsSSOInlinePolicy"],
                "Unexpected inline attachments",
            )
            require(
                not aws(profile, "iam", "list-attached-role-policies", "--role-name", role)[
                    "AttachedPolicies"
                ],
                "Unexpected managed attachments",
            )
            require(
                aws(
                    profile,
                    "iam",
                    "get-role-policy",
                    "--role-name",
                    role,
                    "--policy-name",
                    "AwsSSOInlinePolicy",
                )["PolicyDocument"]
                == declaration["inline_policy"],
                "Generated policy mismatch",
            )
            assignments = aws(
                approval["owner_profile"],
                "sso-admin",
                "list-account-assignments",
                *args,
                "--account-id",
                account,
            )["AccountAssignments"]
            expected = [a for a in declaration["assignments"] if a["target_account_id"] == account]
            require(
                len(assignments) == len(expected)
                and {(a["PrincipalId"], a["PrincipalType"]) for a in assignments}
                == {(a["principal_id"], a["principal_type"]) for a in expected},
                "Assignment mismatch",
            )
    finally:
        exclusive(evidence, {"calls": calls})


def execute(action, contract_path, approval_path):
    os.umask(0o077)
    env = runtime.environment("preflight" if action == "preflight" else "apply")
    c, baseline, desired = validate(contract_path)
    owner, review = Path(c["owner_directory"]), Path(c["review_directory"])
    manifest = review / "declarative-iam-manifest.json"
    a = approved(
        approval_path,
        "seal" if action == "seal" else "apply",
        contract_path,
        None if action == "seal" else manifest,
    )
    if action == "seal":
        exclusive(
            manifest,
            {
                "contract_sha256": digest(contract_path),
                "workflow_sha256": workflow_hash(),
                "seal_approval_sha256": digest(approval_path),
                "seal_approval_path": str(approval_path),
            },
        )
        return
    m = load(manifest)
    require(
        m["contract_sha256"] == digest(contract_path)
        and m["workflow_sha256"] == workflow_hash()
        and digest(Path(m["seal_approval_path"])) == m["seal_approval_sha256"],
        "Seal tampered",
    )
    approved(Path(m["seal_approval_path"]), "seal", contract_path)
    # Unique directory prevents evidence overwrites; failed preflight is not an apply attempt.
    import tempfile

    evidence = Path(tempfile.mkdtemp(prefix="execution-evidence-", dir=review))
    live(env, a, baseline, evidence / "preflight.json")
    if action == "preflight":
        return
    validate(contract_path)
    require(load(manifest) == m, "Manifest changed during preflight")
    approved(approval_path, "apply", contract_path, manifest)
    attempt = review / "declarative-iam-attempt.json"
    exclusive(
        attempt,
        {
            "status": "started",
            "approval_sha256": digest(approval_path),
            "manifest_sha256": digest(manifest),
        },
    )
    receipt = {"status": "failed-stop-for-human", "terraform_exit_code": None}
    created = []
    try:
        for name in c["source_files"]:
            if not (owner / name).exists():
                with (owner / name).open("xb") as f:
                    f.write((review / name).read_bytes())
                created.append(owner / name)
        # Canonical local backend only. Never execute from the planning copy.
        with (evidence / "terraform.log").open("x") as log:
            result = subprocess.run(
                ["terraform", "apply", "-input=false", "-no-color", str(review / "review.tfplan")],
                cwd=owner,
                env=env | {"AWS_PROFILE": a["owner_profile"]},
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1800,
                check=False,
            )
        receipt["terraform_exit_code"] = result.returncode
        require(result.returncode == 0, "Terraform failed; no retry or rollback")
    finally:
        for path in created:
            require(
                digest(path) == c["source_files"][path.name],
                "Temporary source modified; preserve for review",
            )
            path.unlink()
        exclusive(evidence / "apply-result.json", receipt)
    validate(contract_path, after=True)
    live(env, a, desired, evidence / "postflight.json")
    exclusive(
        evidence / "verified.json",
        {
            "status": "verified",
            "state_sha256": digest(owner / "terraform.tfstate"),
            "reprovisioning_accounts": ACCOUNTS,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "seal", "preflight", "apply"])
    parser.add_argument("--contract-file", type=Path, required=True)
    parser.add_argument("--approval-file", type=Path)
    args = parser.parse_args()
    if args.action == "validate":
        validate(args.contract_file)
    else:
        require(args.approval_file is not None, "Approval file required")
        execute(args.action, args.contract_file, args.approval_file)


if __name__ == "__main__":
    main()
