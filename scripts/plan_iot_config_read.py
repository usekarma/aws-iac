#!/usr/bin/env python3
"""Restricted same-owner plan ONLY: add one IoT config GetParameter resource.

Uses the existing authoritative owner's sealed maintenance validation helpers.
No seal, apply, init, import, state command, config publication or IAM API write.
"""

import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OWNER_REPO = Path("/home/ted/dev/aws-iac")
OWNER = OWNER_REPO / "artifacts/identity-center-bootstrap/review-uhd86fs8"
PUB_REVIEW = "artifact-publisher-hrrbk83v"
PUB_MANIFEST = "684cb6cc5f9a3969670571a5990a3cd6ef01123077f1707d3ec0994f335753be"
RECEIPT = "postflight-rechecks/review-7yolru5o/postflight.json"
RECEIPT_SHA256 = "1c83cb71ba4dc3c94487f0dd7640f5979299327f9eb228d65678914241f2a3a3"
LINEAGE = "adda9261-8df8-2be4-51cf-f829529878b3"
SERIAL = 13
STATE_SHA256 = "221cd1cd4e517b46472888585ddfab1a28aa436cd7c9f07ea9ad4cf41d09906e"
BASE_DECLARATION_SHA256 = "5a490557440fdd826a1ac6ae1f2d8644f12f796114dc2315cdc6baf8a7089bad"
DECLARATION = "examples/identity-center-owner.iac-plan-readonly.iot-config-read.json"
SSM_ARN = "arn:aws:ssm:us-east-1:623155450153:parameter/iac/iot-digital-twin/core2-aws-001/config"
INSTANCE = "arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91"
PS_ARN = "arn:aws:sso:::permissionSet/ssoins-7223e8cbef5c5b91/ps-8f764ca58be6f718"
PUB_ARN = "arn:aws:sso:::permissionSet/ssoins-7223e8cbef5c5b91/ps-3194286a73e46a0e"
PRINCIPAL = "b4486448-d011-7037-9cfb-c16c43f591e1"
POLICY = "aws_ssoadmin_permission_set_inline_policy.inline_policy"
EXPECTED = {
    "aws_ssoadmin_permission_set.permission_set",
    POLICY,
    f'aws_ssoadmin_account_assignment.assignment["623155450153/USER/{PRINCIPAL}"]',
    f'aws_ssoadmin_account_assignment.assignment["835990279085/USER/{PRINCIPAL}"]',
    "aws_ssoadmin_permission_set.artifact_publisher",
    "aws_ssoadmin_permission_set_inline_policy.artifact_publisher",
    f'aws_ssoadmin_account_assignment.artifact_publisher["623155450153/USER/{PRINCIPAL}"]',
}
OVERLAY = "artifact_publisher_additions.tf"


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def declarations():
    new = load(ROOT / DECLARATION)
    old = copy.deepcopy(new)
    statement = next(
        s for s in old["inline_policy"]["Statement"] if s["Sid"] == "ReadBindingAndRuntime"
    )
    if statement["Action"] != "ssm:GetParameter" or statement["Resource"].count(SSM_ARN) != 1:
        raise ValueError("Require exactly one additional reviewed SSM config ARN")
    statement["Resource"].remove(SSM_ARN)
    digest = hashlib.sha256(
        json.dumps(old, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != BASE_DECLARATION_SHA256:
        raise ValueError(
            "Every other policy/identity/assignment/condition must match the exact 32-action baseline"
        )
    return old, new


def guard(env):
    if (
        env.get("AGENT_MODE") != "1"
        or env.get("AWS_PROFILE") != "identity-center-plan"
        or env.get("AWS_REGION") != "us-east-1"
        or env.get("EXPECTED_AWS_ACCOUNT") != "835990279085"
    ):
        raise ValueError(
            "Require AGENT_MODE=1, identity-center-plan, owner 835990279085, us-east-1"
        )
    competing = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
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
    return env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_MAX_ATTEMPTS": "1",
    }


def aws_read(env, *args):
    allowed = {
        ("sts", "get-caller-identity"),
        ("sso-admin", "list-instances"),
        ("sso-admin", "describe-permission-set"),
        ("sso-admin", "get-inline-policy-for-permission-set"),
        ("sso-admin", "list-managed-policies-in-permission-set"),
        ("sso-admin", "list-customer-managed-policy-references-in-permission-set"),
        ("sso-admin", "list-account-assignments"),
        ("sso-admin", "list-tags-for-resource"),
    }
    if args[:2] not in allowed:
        raise ValueError("Read-only maintenance discovery action required")
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
        raise ValueError(
            "Read failed; no fallback or permission expansion: " + result.stderr.strip()
        )
    return json.loads(result.stdout)


def runtime():
    # Existing helpers are loaded from the authoritative repository, not a new owner.
    # Lazy loading keeps deterministic declaration/plan tests independent of private state.
    sys.path.insert(0, str(OWNER_REPO / "scripts"))
    execution = importlib.import_module("maintain_artifact_publisher")
    recovery = importlib.import_module("recheck_artifact_publisher")
    for module in (
        execution,
        recovery,
        execution.owner_workflow,
        execution.maintenance,
        execution.bootstrap,
    ):
        if Path(module.__file__).resolve().parent != OWNER_REPO / "scripts":
            raise ValueError("Use only the existing authoritative maintenance helper sources")
    return execution, recovery


def validate_owner(env, execution, recovery):
    review = OWNER / "maintenance-reviews" / PUB_REVIEW
    execution.verify_manifest(OWNER, review, PUB_MANIFEST, applied=True)
    owner, out, config, state, prior, plan = execution.validate_bundle(
        env, OWNER, review, applied=True
    )
    if owner != OWNER or recovery.validate_applied_state(state, prior, plan, config) != PUB_ARN:
        raise ValueError("Verified publisher/state owner differs")
    if sha(out / RECEIPT) != RECEIPT_SHA256:
        raise ValueError("Verified publisher postflight receipt changed")
    receipt = load(out / RECEIPT)
    if any(
        receipt.get(k) != v
        for k, v in {
            "status": "verified",
            "operation": "artifact-publisher-postflight-recheck",
            "manifest_sha256": PUB_MANIFEST,
            "publisher_permission_set_arn": PUB_ARN,
            "lineage": LINEAGE,
            "serial": SERIAL,
            "state_sha256": STATE_SHA256,
            "second_state_owner": False,
        }.items()
    ):
        raise ValueError("Require the verified retained publisher postflight")
    if receipt.get("verifier_sha256") != sha(
        OWNER_REPO / "scripts/recheck_artifact_publisher.py"
    ) or receipt.get("historical_execution_record_sha256") != execution.safe_hashes(
        out, {"apply.log", "apply-result.json", "post-apply.json"}
    ):
        raise ValueError("Historical postflight/execution provenance changed")
    if (
        state.get("lineage") != LINEAGE
        or state.get("serial") != SERIAL
        or sha(OWNER / "terraform.tfstate") != STATE_SHA256
    ):
        raise ValueError("Exact seven-resource state lineage/serial/hash changed")
    old, _ = declarations()
    managed = execution.owner_workflow.managed_state(state)
    if (
        set(managed) != EXPECTED
        or json.loads(managed[POLICY]["inline_policy"]) != old["inline_policy"]
    ):
        raise ValueError("Authoritative seven-resource/32-action planning baseline differs")
    return state, managed, review


def live_checks(env, managed):
    instances = aws_read(env, "sso-admin", "list-instances")["Instances"]
    if not any(
        i.get("InstanceArn") == INSTANCE and i.get("OwnerAccountId") == "835990279085"
        for i in instances
    ):
        raise ValueError("Instance/owner mismatch")
    for resource, policy_address, arn, accounts in (
        (
            "aws_ssoadmin_permission_set.permission_set",
            POLICY,
            PS_ARN,
            ("623155450153", "835990279085"),
        ),
        (
            "aws_ssoadmin_permission_set.artifact_publisher",
            "aws_ssoadmin_permission_set_inline_policy.artifact_publisher",
            PUB_ARN,
            ("623155450153",),
        ),
    ):
        args = ("--instance-arn", INSTANCE, "--permission-set-arn", arn)
        ps = aws_read(env, "sso-admin", "describe-permission-set", *args)["PermissionSet"]
        attrs = managed[resource]
        if any(
            ps.get(k) != v
            for k, v in {
                "PermissionSetArn": arn,
                "Name": attrs["name"],
                "SessionDuration": "PT1H",
                "Description": attrs["description"],
            }.items()
        ):
            raise ValueError("Permission-set identity/duration/description drift")
        policy = aws_read(env, "sso-admin", "get-inline-policy-for-permission-set", *args)[
            "InlinePolicy"
        ]
        if json.loads(policy) != json.loads(managed[policy_address]["inline_policy"]):
            raise ValueError("Existing live policy differs from retained owner")
        for operation, field in (
            ("list-managed-policies-in-permission-set", "AttachedManagedPolicies"),
            (
                "list-customer-managed-policy-references-in-permission-set",
                "CustomerManagedPolicyReferences",
            ),
        ):
            if aws_read(env, "sso-admin", operation, *args)[field]:
                raise ValueError("Unexpected managed-policy attachment")
        for account in ("623155450153", "835990279085"):
            assignments = aws_read(
                env, "sso-admin", "list-account-assignments", *args, "--account-id", account
            )["AccountAssignments"]
            expected = (
                [
                    {
                        "AccountId": account,
                        "PermissionSetArn": arn,
                        "PrincipalType": "USER",
                        "PrincipalId": PRINCIPAL,
                    }
                ]
                if account in accounts
                else []
            )
            if assignments != expected:
                raise ValueError("Existing USER assignments differ")


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return value is True


def validate_plan(plan, managed, old, new):
    if plan.get("complete") is not True or any(
        plan.get(k) for k in ("errored", "resource_drift", "deferred_changes", "action_invocations")
    ):
        raise ValueError("Incomplete/errored/drifting maintenance plan")
    rows = [r for r in plan.get("resource_changes", []) if r.get("mode", "managed") == "managed"]
    if len(rows) != 7 or {r["address"] for r in rows} != EXPECTED:
        raise ValueError(
            "Only the seven existing resources are allowed; no creates/extra resources"
        )
    for row in rows:
        change = row["change"]
        if (
            row.get("type") != row["address"].split(".")[0]
            or row.get("provider_name") != "registry.terraform.io/hashicorp/aws"
            or row.get("previous_address")
            or change.get("importing")
            or change.get("replace_paths")
        ):
            raise ValueError("No move/import/replacement/provider changes")
        if change["before"] != managed[row["address"]]:
            raise ValueError("Plan before attributes differ from exact retained state")
        if row["address"] != POLICY:
            if change["actions"] != ["no-op"] or change["before"] != change["after"]:
                raise ValueError(
                    "All permission sets, assignments and publisher policy must remain no-op"
                )
        else:
            if change["actions"] != ["update"] or unknown(change.get("after_unknown", {})):
                raise ValueError("Only one fully known in-place planner policy update is allowed")
            before, after = copy.deepcopy(change["before"]), copy.deepcopy(change["after"])
            if (
                json.loads(before.pop("inline_policy")) != old["inline_policy"]
                or json.loads(after.pop("inline_policy")) != new["inline_policy"]
                or before != after
            ):
                raise ValueError("Only the exact one-resource GetParameter delta is allowed")


def plan(env):
    env = guard(env)
    old, new = declarations()
    caller = aws_read(env, "sts", "get-caller-identity")
    if caller.get("Account") != "835990279085" or not re.fullmatch(
        r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_[0-9a-f]+/.+",
        caller.get("Arn", ""),
    ):
        raise ValueError("Wrong owner account/role; no AdministratorAccess planning")
    execution, recovery = runtime()
    state, managed, previous = validate_owner(env, execution, recovery)
    live_checks(env, managed)
    os.umask(0o077)
    out = Path(tempfile.mkdtemp(prefix="iot-config-read-", dir=OWNER / "maintenance-reviews"))
    owner_hashes = execution.safe_hashes(OWNER, execution.owner_files(OWNER))
    repo_hashes = {
        DECLARATION: sha(ROOT / DECLARATION),
        "scripts/plan_iot_config_read.py": sha(ROOT / "scripts/plan_iot_config_read.py"),
    }
    source = (previous / OVERLAY).read_bytes()
    (out / OVERLAY).write_bytes(source)
    variables = load(OWNER / "bootstrap.tfvars.json")
    variables["bootstrap_config_json"] = json.dumps(new)
    (out / "maintenance.tfvars.json").write_text(json.dumps(variables, indent=2) + "\n")
    overlay = OWNER / OVERLAY
    with overlay.open("xb") as f:
        f.write(source)
    try:
        with (out / "terraform.log").open("x") as log:
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
                cwd=OWNER,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                raise ValueError(
                    "Restricted IAM plan failed; inspect private "
                    + str(out / "terraform.log")
                    + "; no permission expansion/retry"
                )
            with (out / "plan.json").open("x") as f:
                subprocess.run(
                    ["terraform", "show", "-json", str(out / "review.tfplan")],
                    cwd=OWNER,
                    env=env,
                    stdout=f,
                    stderr=log,
                    check=True,
                )
    finally:
        overlay.unlink()
        if execution.safe_hashes(OWNER, owner_hashes) != owner_hashes or any(
            sha(ROOT / n) != h for n, h in repo_hashes.items()
        ):
            raise ValueError("Owner/source/state changed; retain evidence without repair")
    rendered = load(out / "plan.json")
    validate_plan(rendered, managed, old, new)
    with zipfile.ZipFile(out / "review.tfplan") as archive:
        names = archive.namelist()
        sources = {"tfconfig/m-/" + p.name: p.read_bytes() for p in OWNER.glob("*.tf")} | {
            "tfconfig/m-/" + OVERLAY: source
        }
        if (
            len(names) != len(set(names))
            or {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            != set(sources)
            or any(archive.read(n) != v for n, v in sources.items())
            or archive.read(".terraform.lock.hcl") != (OWNER / ".terraform.lock.hcl").read_bytes()
            or execution.owner_workflow.managed_state(json.loads(archive.read("tfstate-prev")))
            != managed
        ):
            raise ValueError("Binary plan source/lock/previous-state provenance differs")
    if any(
        {k: v["value"] for k, v in rendered.get("variables", {}).items()}.get(k) != v
        for k, v in variables.items()
    ):
        raise ValueError("Reviewed local declaration variables differ")
    record = {
        "owner_directory": str(OWNER),
        "lineage": state["lineage"],
        "serial": state["serial"],
        "state_sha256": STATE_SHA256,
        "owner_inputs": owner_hashes,
        "proposal_inputs": repo_hashes,
        "identity": caller,
        "granted_resource": SSM_ARN,
        "saved_plan_sha256": sha(out / "review.tfplan"),
        "plan_json_sha256": sha(out / "plan.json"),
        "previous_verified_review": str(previous / RECEIPT),
        "previous_review_sha256": sha(previous / RECEIPT),
        "creates": 0,
        "changes": 1,
        "deletes": 0,
        "seal_supported": False,
        "apply_supported": False,
    }
    (out / "owner.json").write_text(json.dumps(record, indent=2) + "\n")
    context = {
        "objective": "Single exact IoT config GetParameter resource addition",
        "repositories": ["aws-iac"],
        "files": [DECLARATION, "scripts/plan_iot_config_read.py"],
        "account": "835990279085",
        "profile": "identity-center-plan",
        "region": "us-east-1",
        "environment": "identity-center-control-plane",
        "binding": "existing retained local owner",
        "prefix": "/iac",
        "component": "identity-center-permission-set",
        "nickname": "owner-iac-plan-readonly",
        "configuration_changes": "One additional exact SSM resource; 32 actions unchanged",
        "validation_results": {
            "plan": "0 creates / 1 policy update / 0 deletes; six original no-ops"
        },
        "blast_radius": "Existing IaCPlanReadOnly inline policy only",
        "recovery": "No execution; any future seal/apply requires separate human review",
        "post_change_checks": [
            "Exact policy and existing assignments/publisher remain intact; restricted workload config probe"
        ],
        "synthetic": False,
    }
    (out / "context.json").write_text(json.dumps(context, indent=2) + "\n")
    execution.publisher.generate(
        out / "plan.json", out / "context.json", out / "evidence", out / "review.tfplan"
    )
    print("STOP_FOR_HUMAN: 0 creates / 1 update / 0 deletes. Review: " + str(out))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan"])
    parser.parse_args()
    plan(dict(os.environ))


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as exc:
        print("STOP_FOR_HUMAN: " + str(exc), file=sys.stderr)
        sys.exit(1)
