#!/usr/bin/env python3
"""Explicit HUMAN-only plan, seal and saved-plan apply for the planning identity."""

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
import zipfile

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
        if resource.get("type") != resource["address"].split(".")[0]:
            raise ValueError("Unexpected bootstrap resource type")
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


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_directory(path):
    raw = Path(path)
    work = raw.resolve(strict=True)
    base = (ROOT / "artifacts/identity-center-bootstrap").resolve()
    if (
        raw.is_symlink()
        or not base.is_relative_to(ROOT.resolve())
        or work.parent != base
        or not work.name.startswith("review-")
        or not work.is_dir()
    ):
        raise ValueError("Use a real bootstrap review directory inside this repository")
    return work


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def repository_identity():
    origin = git("config", "--get", "remote.origin.url")
    if origin not in (
        "git@github.com:usekarma/aws-iac.git",
        "https://github.com/usekarma/aws-iac.git",
        "https://github.com/usekarma/aws-iac",
    ):
        raise ValueError("Bootstrap repository must be usekarma/aws-iac")
    return {"name": "usekarma/aws-iac", "commit": git("rev-parse", "HEAD")}


def verify_ancestor(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise ValueError("Review bundle lacks a valid repository commit")
    subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=True,
        capture_output=True,
    )


def bundle_files(work):
    names = {
        "review.tfplan",
        "plan.json",
        "context.json",
        "discovery.json",
        "bootstrap.tfvars.json",
        "bootstrap_override.tf",
        ".terraform.lock.hcl",
        ".terraform/terraform.tfstate",
        "evidence/evidence.json",
        "evidence/summary.md",
    } | {p.name for p in (ROOT / "components" / COMPONENT).glob("*.tf")}
    for name in names:
        path = work / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(work):
            raise ValueError("Missing or unsafe review file: " + name)
    if {p.name for p in work.glob("*.tf")} != {n for n in names if n.endswith(".tf")}:
        raise ValueError("Unexpected Terraform configuration in review directory")
    if (
        (work / "terraform.tfstate").exists()
        or list(work.glob("*.auto.tfvars*"))
        or list(work.glob("*.tf.json"))
    ):
        raise ValueError(
            "Review directory has state or automatic variable overrides; stop for review"
        )
    backend = load(work / ".terraform/terraform.tfstate").get("backend", {})
    if (
        backend.get("type") != "local"
        or backend.get("config") != {"path": None, "workspace_dir": None}
        or (work / ".terraform/environment").exists()
    ):
        raise ValueError(
            "Bootstrap backend/workspace metadata changed; only default local state is permitted"
        )
    return sorted(names)


def read_saved_plan(work, env):
    result = subprocess.run(
        ["terraform", "show", "-json", "review.tfplan"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("Cannot re-export saved plan; no mutation permitted")
    return json.loads(result.stdout)


def validate_bundle(work, env):
    files = bundle_files(work)
    config = load(ROOT / DECLARATION)
    validate_declaration(config)
    context = load(work / "context.json")
    expected_context = {
        "account": OWNER,
        "profile": env["AWS_PROFILE"],
        "region": "us-east-1",
        "component": COMPONENT,
        "nickname": "owner-iac-plan-readonly",
    }
    if context.get("synthetic") is not False or any(
        context.get(k) != v for k, v in expected_context.items()
    ):
        raise ValueError("Review context identity differs from this bootstrap")
    evidence = load(work / "evidence/evidence.json")
    verify_ancestor(evidence.get("repository_commit"))
    if (
        evidence.get("source", {}).get("synthetic") is not False
        or evidence["source"].get("saved_plan_sha256") != sha256(work / "review.tfplan")
        or evidence["source"].get("plan_json_sha256") != sha256(work / "plan.json")
    ):
        raise ValueError("Original evidence hashes differ from saved plan/JSON")
    if (
        evidence.get("context") != {key: context[key] for key in evidence.get("context", {})}
        or evidence.get("context", {}).get("component") != COMPONENT
    ):
        raise ValueError("Evidence context differs from review context")
    for source in (ROOT / "components" / COMPONENT).glob("*.tf"):
        if source.read_bytes() != (work / source.name).read_bytes():
            raise ValueError("Component changed since planning; require a new reviewed plan")
    expected_vars = {
        "component_name": COMPONENT,
        "nickname": "owner-iac-plan-readonly",
        "region": "us-east-1",
        "administration_account_id": OWNER,
        "bootstrap_config_json": json.dumps(config),
    }
    if load(work / "bootstrap.tfvars.json") != expected_vars:
        raise ValueError("Review declaration variables differ from checked-in declaration")
    if (work / "bootstrap_override.tf").read_text() != 'terraform {\n  backend "local" {}\n}\n':
        raise ValueError("Bootstrap must retain its reviewed local backend")
    with zipfile.ZipFile(work / "review.tfplan") as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Saved plan archive contains duplicate entries")
        expected_sources = {"tfconfig/m-/" + name for name in files if name.endswith(".tf")}
        actual_sources = {
            name
            for name in archive.namelist()
            if name.startswith("tfconfig/") and name.endswith((".tf", ".tf.json"))
        }
        if actual_sources != expected_sources:
            raise ValueError("Saved plan contains unexpected Terraform source")
        for name in expected_sources:
            if archive.read(name) != (work / name.removeprefix("tfconfig/m-/")).read_bytes():
                raise ValueError("Saved plan source differs from reviewed component snapshot")
        if archive.read(".terraform.lock.hcl") != (work / ".terraform.lock.hcl").read_bytes():
            raise ValueError("Provider lock differs from saved plan")
    stored = load(work / "plan.json")
    exported = read_saved_plan(work, env)
    if exported != stored:
        raise ValueError("Saved binary plan does not match reviewed plan.json")
    validate_plan(exported, config)
    variables = {k: v["value"] for k, v in exported.get("variables", {}).items()}
    if any(variables.get(k) != v for k, v in expected_vars.items()):
        raise ValueError("Saved plan variables differ from reviewed declaration")
    return files


def seal_bundle(env, path):
    guard(env)
    work = review_directory(path)
    manifest_path = work / "review-manifest.json"
    if manifest_path.exists():
        raise ValueError("Manifest already exists; never overwrite or silently reseal review")
    files = validate_bundle(work, env)
    manifest = {
        "schema_version": 1,
        "component": COMPONENT,
        "account": OWNER,
        "review_directory": str(work),
        "repository": repository_identity(),
        "files": {name: sha256(work / name) for name in files},
        "repository_inputs": {
            name: sha256(ROOT / name)
            for name in [DECLARATION, "scripts/bootstrap_identity_center.py", "scripts/evidence.py"]
        },
    }
    os.umask(0o077)
    with manifest_path.open("x") as output:
        output.write(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o400)
    print(
        "Review manifest created without regenerating the plan. Record/review this SHA-256: "
        + sha256(manifest_path)
    )
    return sha256(manifest_path)


def verify_manifest(work, expected_digest):
    manifest_path = work / "review-manifest.json"
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_digest or "")
        or manifest_path.is_symlink()
        or sha256(manifest_path) != expected_digest
    ):
        raise ValueError("Manifest differs from explicitly supplied reviewed digest")
    manifest = load(manifest_path)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("component") != COMPONENT
        or manifest.get("account") != OWNER
        or manifest.get("review_directory") != str(work)
        or manifest.get("repository", {}).get("name") != repository_identity()["name"]
    ):
        raise ValueError("Manifest repository/component/target identity mismatch")
    verify_ancestor(manifest["repository"]["commit"])
    if set(manifest["files"]) != set(bundle_files(work)):
        raise ValueError("Manifest review file inventory differs")
    for name, digest in manifest["files"].items():
        if sha256(work / name) != digest:
            raise ValueError("Review input changed after sealing: " + name)
    expected_inputs = {DECLARATION, "scripts/bootstrap_identity_center.py", "scripts/evidence.py"}
    if set(manifest.get("repository_inputs", {})) != expected_inputs:
        raise ValueError("Manifest repository input inventory differs")
    for name, digest in manifest["repository_inputs"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Repository review input changed after sealing: " + name)


def postflight(env, work, config):
    result_path = work / "post-apply.json"
    try:
        matches = []
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
            if item["Name"] == "IaCPlanReadOnly":
                matches.append(item)
        if len(matches) != 1 or matches[0].get("SessionDuration") != "PT1H":
            raise ValueError("Postflight permission set/duration mismatch")
        arn = matches[0]["PermissionSetArn"]
        args = ("--instance-arn", INSTANCE, "--permission-set-arn", arn)
        policy = aws(env, "sso-admin", "get-inline-policy-for-permission-set", *args)[
            "InlinePolicy"
        ]
        managed = aws(env, "sso-admin", "list-managed-policies-in-permission-set", *args)[
            "AttachedManagedPolicies"
        ]
        customer = aws(
            env, "sso-admin", "list-customer-managed-policy-references-in-permission-set", *args
        )["CustomerManagedPolicyReferences"]
        assignments = aws(
            env, "sso-admin", "list-account-assignments", *args, "--account-id", "623155450153"
        )["AccountAssignments"]
        if json.loads(policy) != config["inline_policy"] or managed or customer:
            raise ValueError("Postflight policy mismatch or managed policies attached")
        if not any(
            a.get("AccountId") == "623155450153"
            and a.get("PrincipalType") == "USER"
            and a.get("PrincipalId") == PRINCIPAL
            for a in assignments
        ):
            raise ValueError("Postflight USER assignment missing")
        result_path.write_text(
            json.dumps(
                {
                    "status": "verified",
                    "account": OWNER,
                    "permission_set_arn": arn,
                    "inline_policy_exact": True,
                    "managed_policies": [],
                    "customer_managed_policies": [],
                    "session_duration": "PT1H",
                    "target_account": "623155450153",
                    "principal_type": "USER",
                    "principal_id": PRINCIPAL,
                },
                indent=2,
            )
            + "\n"
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result_path.write_text(
            json.dumps({"status": "failed", "reason": str(exc), "mutation_already_performed": True})
            + "\n"
        )
        raise


def apply_bootstrap(env, path, manifest_digest):
    guard(env)
    if env.get("AWS_MUTATION_APPROVED") != "1":
        raise ValueError(
            "Apply additionally requires AWS_MUTATION_APPROVED=1 after explicit approval"
        )
    env = env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    os.umask(0o077)
    work = review_directory(path)
    verify_manifest(work, manifest_digest)
    validate_bundle(work, env)
    discover(env)
    # Repeat digest checks immediately before mutation; never init or replan here.
    verify_manifest(work, manifest_digest)
    with (work / "apply.log").open("x") as log:
        result = subprocess.run(
            ["terraform", "apply", "-input=false", "-no-color", "review.tfplan"],
            cwd=work,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise ValueError(
            "Apply failed and may be partial; inspect private apply.log/state. Do not retry automatically."
        )
    postflight(env, work, load(ROOT / DECLARATION))
    print(
        "Human bootstrap apply and read-only postflight completed. Retain local state; no profile configured."
    )


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
        "STOP_FOR_HUMAN: 3 creates, 0 changes, 0 deletes. Seal/review this bundle before any separately approved apply."
    )
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "seal", "apply"])
    parser.add_argument("component", choices=[COMPONENT])
    parser.add_argument("--review-dir")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action == "plan":
        if args.review_dir or args.manifest_sha256:
            parser.error("plan does not accept review/apply arguments")
        plan_bootstrap(dict(os.environ))
    elif not args.review_dir:
        parser.error("seal/apply requires --review-dir")
    elif args.action == "seal":
        if args.manifest_sha256:
            parser.error("seal does not accept a manifest digest")
        seal_bundle(dict(os.environ), args.review_dir)
    elif not args.manifest_sha256:
        parser.error("apply requires the independently reviewed --manifest-sha256")
    else:
        apply_bootstrap(dict(os.environ), args.review_dir, args.manifest_sha256)


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
