#!/usr/bin/env python3
"""Human-only exact saved-plan apply/postflight. No planning, retry, or rollback."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import seal_m1_discovery as seal

MANIFEST_HASH = "666c5e8f55bc840e1c937d8d1b499ed9f0dee270f5574e88d7266c4e0753be16"
ROLES = {
    "623155450153": "AWSReservedSSO_IaCPlanReadOnly_92e4b2f1ca02a611",
    "835990279085": "AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b",
}
INSTANCE = "arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91"
PS = "arn:aws:sso:::permissionSet/ssoins-7223e8cbef5c5b91/ps-8f764ca58be6f718"


def environment():
    if os.environ.get("AGENT_MODE") != "0" or os.environ.get("HUMAN_M1_APPLY_APPROVED") != "1":
        raise ValueError("Human terminal only: AGENT_MODE=0 and explicit apply approval required")
    for key, value in os.environ.items():
        if value and (
            key
            in {
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
                "AWS_SECURITY_TOKEN",
                "AWS_ROLE_ARN",
                "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                "TF_DATA_DIR",
                "TF_WORKSPACE",
                "TF_CLI_CONFIG_FILE",
            }
            or key.startswith(("TF_CLI_ARGS", "TF_VAR_", "TG_", "TERRAGRUNT_", "AWS_ENDPOINT_URL"))
        ):
            raise ValueError("Competing override: " + key)
    return dict(
        os.environ,
        AWS_REGION="us-east-1",
        AWS_DEFAULT_REGION="us-east-1",
        AWS_PAGER="",
        AWS_MAX_ATTEMPTS="1",
        AWS_EC2_METADATA_DISABLED="true",
    )


def aws(env, profile, *args):
    result = subprocess.run(
        ["aws", "--profile", profile, "--region", "us-east-1", "--no-cli-pager", *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def guard_identity(env, profile, expected_arn, account):
    identity = aws(env, profile, "sts", "get-caller-identity")
    if identity["Account"] != account or identity["Arn"] != expected_arn:
        raise ValueError("Approved operator identity mismatch")
    return identity


def approval(path):
    value = seal.load(path)
    if set(value) != {
        "operation",
        "approved",
        "plan_sha256",
        "manifest_sha256",
        "reprovisioning_accounts",
        "owner_profile",
        "owner_identity_arn",
        "target_read_profile",
        "target_read_identity_arn",
        "workflow_sha256",
    } or (
        value["operation"] != "m1-discovery-exact-apply"
        or value["approved"] is not True
        or value["workflow_sha256"] != seal.digest(Path(__file__))
        or value["plan_sha256"] != seal.PLAN_HASH
        or value["manifest_sha256"] != MANIFEST_HASH
        or value["reprovisioning_accounts"] != seal.ACCOUNTS
        or value["owner_profile"] != "identity-center-admin"
        or not re.fullmatch(
            r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_[0-9a-f]+/.+",
            value["owner_identity_arn"],
        )
        or not re.fullmatch(
            r"arn:aws:sts::623155450153:assumed-role/[^/]+/.+", value["target_read_identity_arn"]
        )
        or not value["target_read_profile"]
    ):
        raise ValueError("Explicit exact-plan/both-account apply approval missing")
    return value


def manifest(owner, review, after=False):
    path = review / "m1-maintenance-manifest.json"
    if seal.digest(path) != MANIFEST_HASH:
        raise ValueError("Approved manifest hash mismatch")
    value = seal.load(path)
    if (
        value["contract"] != "m1-discovery-seal-only-v1"
        or value["owner_directory"] != str(owner)
        or owner != seal.OWNER
        or value["review_directory"] != str(review)
        or value["plan_sha256"] != seal.PLAN_HASH
        or value["eventual_reprovisioning_accounts"] != seal.ACCOUNTS
        or value["apply_authorized"] is not False
    ):
        raise ValueError("Sealed contract mismatch")
    for name, expected in value["review_files"].items():
        if seal.digest(review / name) != expected:
            raise ValueError("Sealed review evidence changed")
    for name, expected in value["repository_inputs"].items():
        if seal.digest(seal.contract.ROOT / name) != expected:
            raise ValueError("Sealed source changed")
    for name, expected in value["owner_files"].items():
        if after and Path(name) == owner / "terraform.tfstate":
            continue
        if seal.digest(Path(name)) != expected:
            raise ValueError("Owner integrity mismatch")
    if seal.digest(review / "review.tfplan") != seal.PLAN_HASH:
        raise ValueError("Saved-plan hash mismatch")
    return value


def state_after(owner, review):
    state = seal.load(owner / "terraform.tfstate")
    if state["lineage"] != "adda9261-8df8-2be4-51cf-f829529878b3" or state["serial"] <= 15:
        raise ValueError("Applied state lineage/serial mismatch")
    actual = {}
    for resource in state["resources"]:
        if resource["mode"] != "managed":
            continue
        for item in resource["instances"]:
            name = resource["type"] + "." + resource["name"]
            if "index_key" in item:
                name += "[" + json.dumps(item["index_key"]) + "]"
            if resource.get("module"):
                name = resource["module"] + "." + name
            if name in actual:
                raise ValueError("Duplicate managed state address")
            actual[name] = item["attributes"]
    expected = {
        row["address"]: row["change"]["after"]
        for row in seal.load(review / "plan.json")["resource_changes"]
        if row.get("mode", "managed") == "managed"
    }
    if actual != expected:
        raise ValueError("Applied resources differ from exact reviewed after-state")
    return state


def live_before(env, approved):
    old, _ = seal.contract.declarations()
    verify_live(env, approved, old)


def verify_live(env, approved, expected=None):
    _, new = seal.contract.declarations()
    if expected is not None:
        new = expected
    args = ("--instance-arn", INSTANCE, "--permission-set-arn", PS)
    inline = aws(
        env, approved["owner_profile"], "sso-admin", "get-inline-policy-for-permission-set", *args
    )
    if json.loads(inline["InlinePolicy"]) != new["inline_policy"]:
        raise ValueError("Live permission set mismatch")
    provisioned = aws(
        env,
        approved["owner_profile"],
        "sso-admin",
        "list-accounts-for-provisioned-permission-set",
        *args,
        "--provisioning-status",
        "LATEST_PERMISSION_SET_PROVISIONED",
    )
    if set(provisioned["AccountIds"]) != set(seal.ACCOUNTS):
        raise ValueError("Both accounts are not latest-provisioned")
    for account in seal.ACCOUNTS:
        profile = (
            approved["owner_profile"]
            if account == "835990279085"
            else approved["target_read_profile"]
        )
        arn = (
            approved["owner_identity_arn"]
            if account == "835990279085"
            else approved["target_read_identity_arn"]
        )
        guard_identity(env, profile, arn, account)
        role = aws(env, profile, "iam", "get-role", "--role-name", ROLES[account])["Role"]
        if role.get("PermissionsBoundary"):
            raise ValueError("Unexpected boundary")
        policies = aws(env, profile, "iam", "list-role-policies", "--role-name", ROLES[account])[
            "PolicyNames"
        ]
        if (
            len(policies) != 1
            or aws(
                env, profile, "iam", "list-attached-role-policies", "--role-name", ROLES[account]
            )["AttachedPolicies"]
        ):
            raise ValueError("Unexpected generated-role policy attachments")
        document = aws(
            env,
            profile,
            "iam",
            "get-role-policy",
            "--role-name",
            ROLES[account],
            "--policy-name",
            policies[0],
        )["PolicyDocument"]
        if document != new["inline_policy"]:
            raise ValueError("Generated role did not receive exact policy")
        assignments = aws(
            env,
            approved["owner_profile"],
            "sso-admin",
            "list-account-assignments",
            *args,
            "--account-id",
            account,
        )["AccountAssignments"]
        expected = [a for a in new["assignments"] if a["target_account_id"] == account]
        if {(a["PrincipalType"], a["PrincipalId"]) for a in assignments} != {
            (a["principal_type"], a["principal_id"]) for a in expected
        }:
            raise ValueError("Assignment drift")


def postflight(env, owner, review, approved):
    manifest(owner, review, after=True)
    state = state_after(owner, review)
    verify_live(env, approved)
    return {
        "status": "verified",
        "serial": state["serial"],
        "lineage": state["lineage"],
        "state_sha256": seal.digest(owner / "terraform.tfstate"),
        "reprovisioning_accounts": seal.ACCOUNTS,
    }


def execute(action, owner, review, approval_path):
    env = environment()
    approved = approval(approval_path)
    guard_identity(env, approved["owner_profile"], approved["owner_identity_arn"], "835990279085")
    os.umask(0o077)
    if action == "postflight":
        # Only explicit read-only verification after a recorded successful attempt.
        attempt = seal.load(review / "m1-apply-receipt.json")
        if attempt.get("terraform_exit_code") != 0 or attempt.get("approval_sha256") != seal.digest(
            approval_path
        ):
            raise ValueError("No matching successful apply attempt")
        result = postflight(env, owner, review, approved)
        with (review / "m1-postflight-receipt.json").open("x") as output:
            output.write(json.dumps(result, indent=2) + "\n")
        return
    manifest(owner, review)
    seal.validate(owner, review)
    live_before(env, approved)
    receipt_path = review / "m1-apply-receipt.json"
    receipt = {
        "status": "attempt-started",
        "approval_sha256": seal.digest(approval_path),
        "manifest_sha256": MANIFEST_HASH,
        "plan_sha256": seal.PLAN_HASH,
        "operator_arn": approved["owner_identity_arn"],
        "terraform_exit_code": None,
    }
    with receipt_path.open("x") as output:
        output.write(json.dumps(receipt, indent=2) + "\n")
    try:
        with (review / "m1-apply.log").open("x") as log:
            result = subprocess.run(
                ["terraform", "apply", "-input=false", "-no-color", str(review / "review.tfplan")],
                cwd=owner,
                env=dict(env, AWS_PROFILE=approved["owner_profile"]),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1800,
                check=False,
            )
        receipt["terraform_exit_code"] = result.returncode
        if result.returncode:
            raise ValueError("Terraform failed; no automatic retry/rollback")
        receipt["postflight"] = postflight(env, owner, review, approved)
        receipt["status"] = "verified"
    except Exception as exc:
        receipt["status"] = "failed-stop-for-human"
        receipt["failure_type"] = type(exc).__name__
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["apply", "postflight"])
    parser.add_argument("--owner-dir", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--approval-file", type=Path, required=True)
    args = parser.parse_args()
    execute(args.action, args.owner_dir, args.review_dir, args.approval_file)


if __name__ == "__main__":
    main()
