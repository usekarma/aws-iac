#!/usr/bin/env python3
"""Explicit HUMAN-only, plan-only bootstrap of the reviewed planning identity."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from evidence import generate, load

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = "identity-center-permission-set"
OWNER = "835990279085"
INSTANCE = "arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91"
PRINCIPAL = "b4486448-d011-7037-9cfb-c16c43f591e1"
DECLARATION = "examples/identity-center-owner.iac-plan-readonly.json"
POLICY_DIGEST = "43f0d7d3f42e95037872b8e90ec11228f2ab869382fdc13c27b493b3e5423d0e"
ASSIGNMENT = f'aws_ssoadmin_account_assignment.assignment["623155450153/USER/{PRINCIPAL}"]'
EXPECTED = {
    "aws_ssoadmin_permission_set.permission_set",
    "aws_ssoadmin_permission_set_inline_policy.inline_policy",
    ASSIGNMENT,
}


def guard(env):
    if env.get("AGENT_MODE", "0") != "0":
        raise ValueError("Agents never use bootstrap; AGENT_MODE must be 0")
    if env.get("HUMAN_BOOTSTRAP_APPROVED") != "1":
        raise ValueError(
            "Explicit HUMAN_BOOTSTRAP_APPROVED=1 is required; it is not apply approval"
        )
    if not env.get("AWS_PROFILE") or env.get("AWS_REGION") != "us-east-1":
        raise ValueError("A named owner profile and explicit AWS_REGION=us-east-1 are required")
    if env.get("EXPECTED_AWS_ACCOUNT") != OWNER:
        raise ValueError("EXPECTED_AWS_ACCOUNT must be exactly " + OWNER)
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


def validate_declaration(config):
    expected_assignment = [
        {
            "target_account_id": "623155450153",
            "principal_type": "USER",
            "principal_id": PRINCIPAL,
        }
    ]
    expected = {
        "administration_account_id": OWNER,
        "instance_arn": INSTANCE,
        "permission_set_name": "IaCPlanReadOnly",
        "session_duration": "PT1H",
        "assignments": expected_assignment,
    }
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError("Bootstrap declaration differs from reviewed identity/assignment")
    digest = hashlib.sha256(
        json.dumps(config["inline_policy"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != POLICY_DIGEST:
        raise ValueError("Inline policy differs from the exact reviewed 24-action policy")


def aws(env, *args):
    result = subprocess.run(
        [
            "aws",
            "--profile",
            env["AWS_PROFILE"],
            "--region",
            "us-east-1",
            *args,
            "--output",
            "json",
            "--no-cli-pager",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # Only discovery commands reach this helper; never print config/state values.
        raise ValueError("Read-only AWS discovery failed: " + result.stderr.strip())
    return json.loads(result.stdout)


def discover(env):
    identity = aws(env, "sts", "get-caller-identity")
    if identity.get("Account") != OWNER:
        raise ValueError("Wrong bootstrap account; stopping before Identity Center discovery")
    if not re.fullmatch(
        r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_[0-9a-f]+/.+",
        identity.get("Arn", ""),
    ):
        raise ValueError("Human bootstrap requires the verified owner AdministratorAccess role")
    instances = aws(env, "sso-admin", "list-instances")["Instances"]
    if not any(
        i.get("InstanceArn") == INSTANCE and i.get("OwnerAccountId") == OWNER for i in instances
    ):
        raise ValueError("Reviewed Identity Center instance/owner not found")
    names = []
    for arn in aws(env, "sso-admin", "list-permission-sets", "--instance-arn", INSTANCE)[
        "PermissionSets"
    ]:
        item = aws(
            env,
            "sso-admin",
            "describe-permission-set",
            "--instance-arn",
            INSTANCE,
            "--permission-set-arn",
            arn,
        )["PermissionSet"]
        names.append(item["Name"])
    if "IaCPlanReadOnly" in names:
        raise ValueError("IaCPlanReadOnly already exists; no duplicate bootstrap plan permitted")
    if "AdministratorAccess" not in names:
        raise ValueError("Existing AdministratorAccess permission set was not confirmed")
    return identity, names


def validate_plan(plan, config):
    if plan.get("errored") or plan.get("complete") is not True or plan.get("resource_drift"):
        raise ValueError("Plan is incomplete, errored or contains drift")
    resources = [
        r for r in plan.get("resource_changes", []) if r.get("mode", "managed") == "managed"
    ]
    if len(resources) != 3 or {r["address"] for r in resources} != EXPECTED:
        raise ValueError(
            "Unexpected managed resources; require exactly the three bootstrap resources"
        )
    for resource in resources:
        if resource["change"]["actions"] != ["create"]:
            raise ValueError("Bootstrap permits only creates; change/delete/replacement rejected")
        after = resource["change"]["after"]
        if after.get("instance_arn") != INSTANCE:
            raise ValueError("Unexpected Identity Center instance")
        if resource["address"] == ASSIGNMENT:
            if any(
                after.get(k) != v
                for k, v in {
                    "target_id": "623155450153",
                    "target_type": "AWS_ACCOUNT",
                    "principal_type": "USER",
                    "principal_id": PRINCIPAL,
                }.items()
            ):
                raise ValueError("Plan assignment differs from reviewed USER/account")
        elif resource["address"] == "aws_ssoadmin_permission_set.permission_set":
            if after.get("name") != "IaCPlanReadOnly" or after.get("session_duration") != "PT1H":
                raise ValueError("Plan permission-set name/duration differs")
        elif json.loads(after["inline_policy"]) != config["inline_policy"]:
            raise ValueError("Planned inline policy differs from reviewed policy")


def plan_bootstrap(env):
    guard(env)
    env = env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    config = load(ROOT / DECLARATION)
    validate_declaration(config)
    identity, names = discover(env)
    os.umask(0o077)
    base = ROOT / "artifacts/identity-center-bootstrap"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = Path(tempfile.mkdtemp(prefix="review-", dir=base))
    for source in (ROOT / "components" / COMPONENT).glob("*.tf"):
        shutil.copy2(source, work / source.name)
    # Only this private snapshot replaces the normal S3 backend with local state.
    (work / "bootstrap_override.tf").write_text('terraform {\n  backend "local" {}\n}\n')
    (work / "bootstrap.tfvars.json").write_text(
        json.dumps(
            {
                "component_name": COMPONENT,
                "nickname": "owner-iac-plan-readonly",
                "region": "us-east-1",
                "administration_account_id": OWNER,
                "bootstrap_config_json": json.dumps(config),
            },
            indent=2,
        )
        + "\n"
    )
    (work / "discovery.json").write_text(
        json.dumps({"identity": identity, "permission_set_names": names}, indent=2) + "\n"
    )
    print("Private bootstrap review directory: " + str(work), flush=True)
    commands = [
        ["terraform", "init", "-input=false", "-no-color"],
        ["terraform", "validate", "-no-color"],
        [
            "terraform",
            "plan",
            "-input=false",
            "-lock=false",
            "-no-color",
            "-var-file=bootstrap.tfvars.json",
            "-out=review.tfplan",
        ],
    ]
    with (work / "terraform.log").open("w") as log:
        for command in commands:
            result = subprocess.run(
                command, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT
            )
            if result.returncode:
                raise ValueError(f"{command[1]} failed; inspect private {work / 'terraform.log'}")
        with (work / "plan.json").open("w") as output:
            subprocess.run(
                ["terraform", "show", "-json", "review.tfplan"],
                cwd=work,
                env=env,
                stdout=output,
                stderr=log,
                check=True,
            )
    validate_plan(load(work / "plan.json"), config)
    context = {
        "objective": "Human-only IaCPlanReadOnly bootstrap; proposal, no apply authorized",
        "repositories": ["aws-iac"],
        "files": [DECLARATION, "components/" + COMPONENT],
        "account": OWNER,
        "profile": env["AWS_PROFILE"],
        "region": "us-east-1",
        "environment": "human-bootstrap-control-plane",
        "binding": "not used: local reviewed declaration",
        "prefix": "/iac",
        "component": COMPONENT,
        "nickname": "owner-iac-plan-readonly",
        "configuration_changes": "Local reviewed declaration; no SSM publication",
        "validation_results": {
            "live_plan": "Exactly three creates; exact reviewed policy and assignment"
        },
        "blast_radius": "One new permission set, inline policy and USER assignment",
        "recovery": "No mutation performed; future revocation requires reviewed approval",
        "post_change_checks": [
            "Verify exact policy, no managed attachments, USER assignment and planning identity"
        ],
        "synthetic": False,
    }
    (work / "context.json").write_text(json.dumps(context, indent=2) + "\n")
    generate(work / "plan.json", work / "context.json", work / "evidence", work / "review.tfplan")
    print(
        "STOP_FOR_HUMAN: 3 creates, 0 changes, 0 deletes. Review private plan/evidence; no apply path is provided."
    )
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan"])
    parser.add_argument("component", choices=[COMPONENT])
    parser.parse_args()
    plan_bootstrap(dict(os.environ))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print("STOP_FOR_HUMAN: " + str(exc), file=sys.stderr)
        sys.exit(1)
