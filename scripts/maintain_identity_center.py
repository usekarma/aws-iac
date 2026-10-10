#!/usr/bin/env python3
"""HUMAN-only sealed saved-plan maintenance of the existing bootstrap state owner."""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

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
        env.get("AWS_PROFILE") != "identity-center-admin"
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


def review_directory(owner, review):
    raw = Path(review)
    out = raw.resolve(strict=True)
    if (
        raw.is_symlink()
        or out.parent != owner / "maintenance-reviews"
        or not out.name.startswith("config-read-")
        or not out.is_dir()
    ):
        raise ValueError("Use a maintenance review beneath the retained original owner")
    return out


def inventories(owner, out):
    review_names = {
        "review.tfplan",
        "plan.json",
        "context.json",
        "owner.json",
        "maintenance.tfvars.json",
        "evidence/evidence.json",
        "evidence/summary.md",
    }
    owner_names = {
        "terraform.tfstate",
        "review-manifest.json",
        "post-apply.json",
        "bootstrap.tfvars.json",
        "bootstrap_override.tf",
        ".terraform.lock.hcl",
        ".terraform/terraform.tfstate",
    } | {p.name for p in (ROOT / "components" / bootstrap.COMPONENT).glob("*.tf")}
    for base, names in ((out, review_names), (owner, owner_names)):
        for name in names:
            file = base / name
            if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(base):
                raise ValueError("Missing/unsafe maintenance review input: " + name)
    return sorted(owner_names), sorted(review_names)


def read_saved_plan(owner, out, env):
    result = subprocess.run(
        ["terraform", "show", "-json", str(out / "review.tfplan")],
        cwd=owner,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("Cannot export saved maintenance plan; no mutation allowed")
    return json.loads(result.stdout)


def validate_review(owner_path, review_path, env):
    old, new = declarations()
    owner, state, arn = validate_owner(owner_path, old)
    out = review_directory(owner, review_path)
    inventories(owner, out)
    recorded = load(out / "owner.json")
    expected = {
        "owner_directory": str(owner),
        "lineage": state["lineage"],
        "serial": state["serial"],
        "state_sha256": bootstrap.sha256(owner / "terraform.tfstate"),
        "declaration_sha256": bootstrap.sha256(ROOT / DECLARATION),
    }
    if any(recorded.get(k) != v for k, v in expected.items()):
        raise ValueError("Owner state/declaration changed since maintenance planning")
    context = load(out / "context.json")
    if context.get("synthetic") is not False or any(
        context.get(k) != v
        for k, v in {
            "component": bootstrap.COMPONENT,
            "account": bootstrap.OWNER,
            "region": "us-east-1",
            "profile": env["AWS_PROFILE"],
        }.items()
    ):
        raise ValueError("Maintenance review identity/context mismatch")
    evidence = load(out / "evidence/evidence.json")
    bootstrap.verify_ancestor(evidence.get("repository_commit"))
    if (
        evidence.get("source", {}).get("synthetic") is not False
        or evidence["source"].get("plan_json_sha256") != bootstrap.sha256(out / "plan.json")
        or evidence["source"].get("saved_plan_sha256") != bootstrap.sha256(out / "review.tfplan")
    ):
        raise ValueError("Original maintenance evidence plan digests differ")
    if (
        evidence.get("context") != {k: context[k] for k in evidence.get("context", {})}
        or evidence.get("context", {}).get("component") != bootstrap.COMPONENT
    ):
        raise ValueError("Maintenance evidence/context mismatch")
    inputs = load(owner / "bootstrap.tfvars.json")
    inputs["bootstrap_config_json"] = json.dumps(new)
    if load(out / "maintenance.tfvars.json") != inputs:
        raise ValueError("Maintenance variables differ from reviewed declaration")
    with zipfile.ZipFile(out / "review.tfplan") as archive:
        names = archive.namelist()
        expected_sources = {"tfconfig/m-/" + p.name for p in owner.glob("*.tf")}
        if (
            len(names) != len(set(names))
            or {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            != expected_sources
        ):
            raise ValueError("Saved maintenance plan source inventory mismatch")
        for name in expected_sources:
            if archive.read(name) != (owner / name.removeprefix("tfconfig/m-/")).read_bytes():
                raise ValueError("Saved maintenance plan source changed")
        if archive.read(".terraform.lock.hcl") != (owner / ".terraform.lock.hcl").read_bytes():
            raise ValueError("Saved maintenance provider lock mismatch")
        # Terraform's in-memory archive omits file lineage/serial; owner.json pins
        # those plus the full live file hash. Verify archived managed states too.
        previous = json.loads(archive.read("tfstate-prev"))

        def managed(s):
            return [r for r in s["resources"] if r["mode"] == "managed"]

        if managed(previous) != managed(state):
            raise ValueError("Saved plan belongs to different managed state")
    plan = read_saved_plan(owner, out, env)
    if plan != load(out / "plan.json"):
        raise ValueError("Saved maintenance binary/JSON differ")
    validate_update(plan, old, new)
    variables = {k: v["value"] for k, v in plan.get("variables", {}).items()}
    if any(variables.get(k) != v for k, v in inputs.items()):
        raise ValueError("Saved maintenance variables differ")
    return owner, out, arn, old, new


def seal_review(env, owner_path, review_path):
    guard(env)
    owner, out, _, _, _ = validate_review(owner_path, review_path, env)
    path = out / "maintenance-manifest.json"
    if path.exists():
        raise ValueError("Never overwrite/reseal an existing maintenance manifest")
    owner_names, review_names = inventories(owner, out)
    manifest = {
        "schema_version": 1,
        "component": bootstrap.COMPONENT,
        "account": bootstrap.OWNER,
        "owner_directory": str(owner),
        "review_directory": str(out),
        "repository": bootstrap.repository_identity(),
        "owner_files": {n: bootstrap.sha256(owner / n) for n in owner_names},
        "review_files": {n: bootstrap.sha256(out / n) for n in review_names},
        "repository_inputs": {
            n: bootstrap.sha256(ROOT / n)
            for n in (
                DECLARATION,
                bootstrap.DECLARATION,
                "scripts/maintain_identity_center.py",
                "scripts/bootstrap_identity_center.py",
                "scripts/evidence.py",
            )
        },
    }
    os.umask(0o077)
    with path.open("x") as output:
        output.write(json.dumps(manifest, indent=2) + "\n")
    path.chmod(0o400)
    digest = bootstrap.sha256(path)
    print(
        "Maintenance manifest sealed without state/plan changes. Independently record SHA-256: "
        + digest
    )
    return digest


def verify_manifest(owner, out, digest):
    path = out / "maintenance-manifest.json"
    if not digest or path.is_symlink() or bootstrap.sha256(path) != digest:
        raise ValueError("Maintenance manifest differs from independently reviewed digest")
    manifest = load(path)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("component") != bootstrap.COMPONENT
        or manifest.get("account") != bootstrap.OWNER
        or manifest.get("owner_directory") != str(owner)
        or manifest.get("review_directory") != str(out)
        or manifest.get("repository", {}).get("name") != bootstrap.repository_identity()["name"]
    ):
        raise ValueError("Maintenance manifest identity mismatch")
    bootstrap.verify_ancestor(manifest["repository"]["commit"])
    owner_names, review_names = inventories(owner, out)
    for base, key, names in (
        (owner, "owner_files", owner_names),
        (out, "review_files", review_names),
    ):
        if set(manifest.get(key, {})) != set(names):
            raise ValueError("Maintenance manifest file inventory mismatch")
        for name in names:
            if bootstrap.sha256(base / name) != manifest[key][name]:
                raise ValueError("Maintenance input changed: " + name)
    expected_inputs = {
        DECLARATION,
        bootstrap.DECLARATION,
        "scripts/maintain_identity_center.py",
        "scripts/bootstrap_identity_center.py",
        "scripts/evidence.py",
    }
    if set(manifest.get("repository_inputs", {})) != expected_inputs:
        raise ValueError("Maintenance manifest repository input inventory mismatch")
    for name, expected in manifest["repository_inputs"].items():
        if bootstrap.sha256(ROOT / name) != expected:
            raise ValueError("Maintenance declaration/script changed: " + name)


def workload_probe(env):
    restricted = env | {
        "AWS_PROFILE": "strall-dev-plan",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
    }
    identity = bootstrap.aws(restricted, "sts", "get-caller-identity")
    if identity.get("Account") != "623155450153" or not identity.get("Arn", "").startswith(
        "arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_IaCPlanReadOnly_"
    ):
        raise ValueError("Postflight workload identity mismatch")
    result = subprocess.run(
        [
            "aws",
            "--profile",
            "strall-dev-plan",
            "--region",
            "us-east-1",
            "ssm",
            "get-parameter",
            "--name",
            "/iac/s3-bucket/iot-digital-twin-artifacts/config",
            "--query",
            "Parameter.Version",
            "--output",
            "json",
            "--no-cli-pager",
        ],
        env=restricted,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return "GetParameter permitted; parameter exists"
    if (
        "(ParameterNotFound) when calling the GetParameter operation" in result.stderr
        and "AccessDenied" not in result.stderr
    ):
        return "GetParameter permitted; ParameterNotFound"
    raise ValueError("Postflight restricted config read failed: " + result.stderr.strip())


def maintenance_apply(env, owner_path, review_path, digest):
    guard(env)
    if env.get("AWS_MUTATION_APPROVED") != "1":
        raise ValueError("Maintenance apply additionally requires AWS_MUTATION_APPROVED=1")
    env = env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    owner = bootstrap.review_directory(owner_path)
    out = review_directory(owner, review_path)
    if (out / "apply.log").exists() or (out / "post-apply.json").exists():
        raise ValueError(
            "Maintenance execution already attempted; inspect retained state/logs, never retry automatically"
        )
    verify_manifest(owner, out, digest)
    owner, out, arn, old, new = validate_review(owner, out, env)
    live_checks(env, arn, old)
    verify_manifest(owner, out, digest)
    os.umask(0o077)
    with (out / "apply.log").open("x") as log:
        result = subprocess.run(
            ["terraform", "apply", "-input=false", "-no-color", str(out / "review.tfplan")],
            cwd=owner,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        (out / "post-apply.json").write_text(
            json.dumps(
                {
                    "status": "apply-failed-may-be-partial",
                    "manifest_sha256": digest,
                    "automatic_retry": False,
                }
            )
            + "\n"
        )
        raise ValueError(
            "Maintenance apply failed; retain state/logs, never retry or rollback automatically"
        )
    try:
        live_checks(env, arn, new)  # Exact new policy proves unchanged 24 actions and one ARN.
        probe = workload_probe(env)
        record = {
            "status": "verified",
            "manifest_sha256": digest,
            "permission_set_arn": arn,
            "session_duration": "PT1H",
            "assignment_unchanged": True,
            "inline_policy_exact": True,
            "original_actions_unchanged": True,
            "managed_policies": [],
            "customer_managed_policies": [],
            "config_read_probe": probe,
        }
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        record = {
            "status": "postflight-failed",
            "manifest_sha256": digest,
            "mutation_already_performed": True,
            "error": str(exc),
            "automatic_retry": False,
        }
        (out / "post-apply.json").write_text(json.dumps(record, indent=2) + "\n")
        raise
    (out / "post-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        "Human maintenance saved-plan apply and read-only postflight verified; retain original owner state."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "seal", "apply"])
    parser.add_argument("component", choices=[bootstrap.COMPONENT])
    parser.add_argument("--owner-dir", required=True)
    parser.add_argument("--review-dir")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action == "plan":
        if args.review_dir or args.manifest_sha256:
            parser.error("plan cannot accept saved-review arguments")
        maintenance_plan(dict(os.environ), args.owner_dir)
    elif not args.review_dir:
        parser.error("seal/apply require --review-dir")
    elif args.action == "seal":
        if args.manifest_sha256:
            parser.error("seal cannot accept a manifest digest")
        seal_review(dict(os.environ), args.owner_dir, args.review_dir)
    elif not args.manifest_sha256:
        parser.error("apply requires independently reviewed --manifest-sha256")
    else:
        maintenance_apply(dict(os.environ), args.owner_dir, args.review_dir, args.manifest_sha256)


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
