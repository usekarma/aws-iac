#!/usr/bin/env python3
"""HUMAN-only plan-only maintenance using the existing bootstrap local state owner."""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import bootstrap_identity_center as bootstrap
from evidence import generate, load

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = "examples/identity-center-owner.iac-plan-readonly.config-read.json"
CONFIG_ARN = (
    "arn:aws:ssm:us-east-1:623155450153:parameter/iac/s3-bucket/iot-digital-twin-artifacts/config"
)
POLICY_ADDRESS = "aws_ssoadmin_permission_set_inline_policy.inline_policy"
OWNER_MANIFEST_SHA256 = "83b7fda1f7f3f66c5311d2199a3f7426862ffd95fbd3341c5826da455ea27c3c"


def guard(env):
    if env.get("AGENT_MODE", "0") != "0":
        raise ValueError("Agents never use human maintenance; AGENT_MODE must be 0")
    if env.get("HUMAN_MAINTENANCE_APPROVED") != "1":
        raise ValueError("Explicit HUMAN_MAINTENANCE_APPROVED=1 required; no apply is authorized")
    if (
        not env.get("AWS_PROFILE")
        or env.get("AWS_REGION") != "us-east-1"
        or env.get("EXPECTED_AWS_ACCOUNT") != bootstrap.OWNER
    ):
        raise ValueError("Require named owner profile, account 835990279085 and us-east-1")
    competing = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_ARN",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "TF_DATA_DIR",
        "TF_WORKSPACE",
        "TF_CLI_CONFIG_FILE",
    }
    for name, value in env.items():
        if value and (
            name in competing
            or name.startswith(("TF_VAR_", "TF_CLI_ARGS", "TG_", "TERRAGRUNT_", "AWS_ENDPOINT_URL"))
        ):
            raise ValueError("Unset competing credential/argument override: " + name)


def declarations():
    old = load(ROOT / bootstrap.DECLARATION)
    bootstrap.validate_declaration(old)  # Preserve the original bootstrap pin/behavior.
    expected = copy.deepcopy(old)
    statement = next(
        s for s in expected["inline_policy"]["Statement"] if s["Sid"] == "ReadBindingAndRuntime"
    )
    statement["Resource"].append(CONFIG_ARN)
    new = load(ROOT / DECLARATION)
    if new != expected:
        raise ValueError("Maintenance declaration may add only the single reviewed config ARN")
    return old, new


def validate_owner(work, old):
    # Resolving the original owner directory never initializes or migrates a backend.
    work = bootstrap.review_directory(work)
    for name in (
        "terraform.tfstate",
        "review-manifest.json",
        "post-apply.json",
        ".terraform/terraform.tfstate",
        "bootstrap.tfvars.json",
    ):
        if not (work / name).is_file() or (work / name).is_symlink():
            raise ValueError("Missing retained owner artifact: " + name)
    if bootstrap.sha256(work / "review-manifest.json") != OWNER_MANIFEST_SHA256:
        raise ValueError("Use only the human-reviewed original owner's manifest")
    postflight = load(work / "post-apply.json")
    if postflight.get("status") != "verified":
        raise ValueError("Original bootstrap postflight must be verified")
    backend = load(work / ".terraform/terraform.tfstate").get("backend", {})
    if (
        backend.get("type") != "local"
        or backend.get("config") != {"path": None, "workspace_dir": None}
        or (work / ".terraform/environment").exists()
    ):
        raise ValueError("Retain default local backend/workspace; no new state owner permitted")
    manifest = load(work / "review-manifest.json")
    if (
        manifest.get("component") != bootstrap.COMPONENT
        or manifest.get("account") != bootstrap.OWNER
        or manifest.get("review_directory") != str(work)
    ):
        raise ValueError("Original manifest owner identity mismatch")
    bootstrap.verify_ancestor(manifest.get("repository", {}).get("commit"))
    for source in (ROOT / "components" / bootstrap.COMPONENT).glob("*.tf"):
        if source.read_bytes() != (work / source.name).read_bytes() or bootstrap.sha256(
            work / source.name
        ) != manifest["files"].get(source.name):
            raise ValueError("Owned Terraform source changed; separate review required")
    expected_files = {p.name for p in (ROOT / "components" / bootstrap.COMPONENT).glob("*.tf")} | {
        "bootstrap_override.tf"
    }
    if (
        {p.name for p in work.glob("*.tf")} != expected_files
        or list(work.glob("*.tf.json"))
        or list(work.glob("*.auto.tfvars*"))
    ):
        raise ValueError("Unexpected owner configuration/variable override")
    for name in (
        "bootstrap_override.tf",
        "bootstrap.tfvars.json",
        ".terraform.lock.hcl",
        ".terraform/terraform.tfstate",
    ):
        if bootstrap.sha256(work / name) != manifest["files"].get(name):
            raise ValueError("Original owner input changed: " + name)
    if json.loads(load(work / "bootstrap.tfvars.json")["bootstrap_config_json"]) != old:
        raise ValueError("Original owner declaration changed")
    state = load(work / "terraform.tfstate")
    if not state.get("lineage") or not isinstance(state.get("serial"), int):
        raise ValueError("Retained state lacks lineage/serial")
    managed = {}
    for r in state["resources"]:
        if r["mode"] != "managed":
            continue
        for instance in r["instances"]:
            address = r["type"] + "." + r["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"]) + "]"
            if address in managed or instance.get("deposed"):
                raise ValueError("Unexpected duplicate/deposed state instance")
            managed[address] = instance["attributes"]
    if set(managed) != bootstrap.EXPECTED:
        raise ValueError("State must own exactly the original three resources")
    ps = managed["aws_ssoadmin_permission_set.permission_set"]
    policy = managed[POLICY_ADDRESS]
    assignment = managed[bootstrap.ASSIGNMENT]
    if postflight.get("permission_set_arn") != ps.get("arn"):
        raise ValueError("State permission set differs from verified original postflight")
    if (
        ps.get("name") != "IaCPlanReadOnly"
        or ps.get("session_duration") != "PT1H"
        or ps.get("instance_arn") != bootstrap.INSTANCE
    ):
        raise ValueError("Retained permission set identity differs")
    if (
        json.loads(policy["inline_policy"]) != old["inline_policy"]
        or policy.get("permission_set_arn") != ps.get("arn")
        or policy.get("instance_arn") != bootstrap.INSTANCE
    ):
        raise ValueError("Retained policy differs from original review")
    if any(
        assignment.get(k) != v
        for k, v in {
            "target_id": "623155450153",
            "target_type": "AWS_ACCOUNT",
            "principal_type": "USER",
            "principal_id": bootstrap.PRINCIPAL,
            "permission_set_arn": ps["arn"],
            "instance_arn": bootstrap.INSTANCE,
        }.items()
    ):
        raise ValueError("Retained assignment identity differs")
    return work, state, ps["arn"]


def live_checks(env, arn, old):
    identity = bootstrap.aws(env, "sts", "get-caller-identity")
    if identity.get("Account") != bootstrap.OWNER or not identity.get("Arn", "").startswith(
        "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_"
    ):
        raise ValueError("Human maintenance requires verified owner AdministratorAccess")
    args = ("--instance-arn", bootstrap.INSTANCE, "--permission-set-arn", arn)
    ps = bootstrap.aws(env, "sso-admin", "describe-permission-set", *args)["PermissionSet"]
    policy = bootstrap.aws(env, "sso-admin", "get-inline-policy-for-permission-set", *args)[
        "InlinePolicy"
    ]
    managed = bootstrap.aws(env, "sso-admin", "list-managed-policies-in-permission-set", *args)[
        "AttachedManagedPolicies"
    ]
    customer = bootstrap.aws(
        env, "sso-admin", "list-customer-managed-policy-references-in-permission-set", *args
    )["CustomerManagedPolicyReferences"]
    assignments = bootstrap.aws(
        env, "sso-admin", "list-account-assignments", *args, "--account-id", "623155450153"
    )["AccountAssignments"]
    if (
        ps.get("Name") != "IaCPlanReadOnly"
        or ps.get("SessionDuration") != "PT1H"
        or json.loads(policy) != old["inline_policy"]
        or managed
        or customer
    ):
        raise ValueError("Live permission set/policy drift; stop without mutation")
    if not any(
        a.get("PrincipalType") == "USER"
        and a.get("PrincipalId") == bootstrap.PRINCIPAL
        and a.get("AccountId") == "623155450153"
        for a in assignments
    ):
        raise ValueError("Live reviewed assignment missing")
    return identity


def has_unknown(value):
    if isinstance(value, dict):
        return any(has_unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(has_unknown(v) for v in value)
    return value is True


def validate_update(plan, old, new):
    if plan.get("complete") is not True or plan.get("errored") or plan.get("resource_drift"):
        raise ValueError("Incomplete/errored/drifting maintenance plan")
    resources = [
        r for r in plan.get("resource_changes", []) if r.get("mode", "managed") == "managed"
    ]
    if len(resources) != 3 or {r["address"] for r in resources} != bootstrap.EXPECTED:
        raise ValueError("Unexpected maintenance resource/state owner")
    for r in resources:
        change = r["change"]
        if r.get("type") != r["address"].split(".")[0]:
            raise ValueError("Unexpected maintenance resource type")
        if r["address"] != POLICY_ADDRESS:
            if change["actions"] != ["no-op"] or change["before"] != change["after"]:
                raise ValueError("Permission set and assignment must be unchanged")
            continue
        if change["actions"] != ["update"] or has_unknown(change.get("after_unknown", {})):
            raise ValueError("Only one fully known in-place policy update is allowed")
        before, after = copy.deepcopy(change["before"]), copy.deepcopy(change["after"])
        if (
            json.loads(before.pop("inline_policy")) != old["inline_policy"]
            or json.loads(after.pop("inline_policy")) != new["inline_policy"]
            or before != after
        ):
            raise ValueError("Plan delta must be the single config ARN only")


def maintenance_plan(env, owner):
    guard(env)
    old, new = declarations()
    work, state, arn = validate_owner(owner, old)
    env = env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    identity = live_checks(env, arn, old)
    os.umask(0o077)
    base = work / "maintenance-reviews"
    base.mkdir(exist_ok=True, mode=0o700)
    out = Path(tempfile.mkdtemp(prefix="config-read-", dir=base))
    state_digest = bootstrap.sha256(work / "terraform.tfstate")
    inputs = load(work / "bootstrap.tfvars.json")
    inputs["bootstrap_config_json"] = json.dumps(new)
    (out / "maintenance.tfvars.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (out / "owner.json").write_text(
        json.dumps(
            {
                "owner_directory": str(work),
                "lineage": state["lineage"],
                "serial": state["serial"],
                "state_sha256": state_digest,
                "declaration_sha256": bootstrap.sha256(ROOT / DECLARATION),
                "identity": identity,
            },
            indent=2,
        )
        + "\n"
    )
    with (out / "terraform.log").open("w") as log:
        result = subprocess.run(
            [
                "terraform",
                "plan",
                "-input=false",
                "-lock=false",
                "-no-color",
                "-var-file=" + str(out / "maintenance.tfvars.json"),
                "-out=" + str(out / "review.tfplan"),
            ],
            cwd=work,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        if result.returncode:
            raise ValueError(
                "Maintenance plan failed; inspect private " + str(out / "terraform.log")
            )
        with (out / "plan.json").open("w") as output:
            subprocess.run(
                ["terraform", "show", "-json", str(out / "review.tfplan")],
                cwd=work,
                env=env,
                stdout=output,
                stderr=log,
                check=True,
            )
    if bootstrap.sha256(work / "terraform.tfstate") != state_digest:
        raise ValueError("Owner state changed during planning; require fresh review")
    validate_update(load(out / "plan.json"), old, new)
    context = {
        "objective": "Human maintenance proposal: single GetParameter config resource grant",
        "repositories": ["aws-iac"],
        "files": [DECLARATION],
        "account": bootstrap.OWNER,
        "profile": env["AWS_PROFILE"],
        "region": "us-east-1",
        "environment": "human-maintenance-control-plane",
        "binding": "not used: original local state owner",
        "prefix": "/iac",
        "component": bootstrap.COMPONENT,
        "nickname": "owner-iac-plan-readonly",
        "configuration_changes": "Single resource ARN; original 24 actions unchanged",
        "validation_results": {
            "plan": "0 creates, 1 policy update, 0 deletes; state digest unchanged"
        },
        "blast_radius": "Existing inline policy only; permission set and assignment unchanged",
        "recovery": "No mutation performed; any future execution/reversal needs separate approval",
        "post_change_checks": [
            "Verify exact updated inline policy and restricted config-path read"
        ],
        "synthetic": False,
    }
    (out / "context.json").write_text(json.dumps(context, indent=2) + "\n")
    generate(out / "plan.json", out / "context.json", out / "evidence", out / "review.tfplan")
    print(
        "STOP_FOR_HUMAN: 0 creates, 1 inline-policy update, 0 deletes. Private evidence: "
        + str(out)
    )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan"])
    parser.add_argument("component", choices=[bootstrap.COMPONENT])
    parser.add_argument("--owner-dir", required=True)
    args = parser.parse_args()
    maintenance_plan(dict(os.environ), args.owner_dir)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print("STOP_FOR_HUMAN: " + str(exc), file=sys.stderr)
        sys.exit(1)
