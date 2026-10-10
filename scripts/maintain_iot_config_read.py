#!/usr/bin/env python3
"""HUMAN-only execution of the reviewed single-ARN IoT config-read IAM update."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import plan_iot_config_read as proposal

ROOT = Path(__file__).resolve().parents[1]
REVIEW_NAME = "iot-config-read-6zmoojc2"
PLAN_SHA256 = "d4ae8ae3ffe728f74a20a3d84a44fc18de18ba2d690bca81b33233aeba9ca839"
PLAN_JSON_SHA256 = "1c11c211aeba2b9a4c9f53f503a9fdd1dfe786ea521865f2229d8d0aa7a9df06"
ORIGINAL_SCRIPT_SHA256 = "37cb47018c28fa72f522b1e5059e872caa7325e8bc4f6085c3ee5a5a34988e4b"
CORRECTED_SCRIPT_SHA256 = "1243ca0a81437cc1f579117751768fe4e75ec1021eef9a8a2f578a780b181f60"
EXECUTOR = "scripts/maintain_iot_config_read.py"
PLANNER = "scripts/plan_iot_config_read.py"
MANIFEST = "iot-config-read-manifest.json"
OPERATION = "iot-config-read"
REVIEW_FILES = {
    "review.tfplan",
    "plan.json",
    "owner.json",
    "context.json",
    "maintenance.tfvars.json",
    "terraform.log",
    proposal.OVERLAY,
    "planning-script.py",
    "evidence-repair.json",
    "evidence/evidence.json",
    "evidence/summary.md",
}


def guard(env, *, mutation=False):
    # Check explicit human mode before loading any private helper or invoking tools.
    if env.get("AGENT_MODE") != "0":
        raise ValueError(
            "IoT config-read seal/apply/postflight is HUMAN-only; AGENT_MODE=0 required"
        )
    if env.get("HUMAN_MAINTENANCE_APPROVED") != "1":
        raise ValueError("Explicit HUMAN_MAINTENANCE_APPROVED=1 required; not mutation approval")
    if mutation and env.get("AWS_MUTATION_APPROVED") != "1":
        raise ValueError("Apply separately requires AWS_MUTATION_APPROVED=1")
    execution, recovery = proposal.runtime()
    return execution.guard(env, mutation=mutation), execution, recovery


def review_directory(owner_path, review_path, execution):
    owner = execution.owner_workflow.owner_directory(owner_path)
    raw = Path(review_path)
    out = raw.resolve(strict=True)
    if (
        owner != proposal.OWNER
        or raw.is_symlink()
        or out != owner / "maintenance-reviews" / REVIEW_NAME
        or not out.is_dir()
    ):
        raise ValueError(
            "Use only the authoritative owner and genuine iot-config-read-6zmoojc2 review"
        )
    return owner, out


def repair_checks(out, execution):
    original = out / "planning-script.py"
    corrected = ROOT / PLANNER
    if (
        proposal.sha(original) != ORIGINAL_SCRIPT_SHA256
        or proposal.sha(corrected) != CORRECTED_SCRIPT_SHA256
    ):
        raise ValueError("Original or explicitly corrected planning source changed")
    before = original.read_bytes()
    if (
        before.count(b"execution.generate(") != 1
        or before.replace(b"execution.generate(", b"execution.publisher.generate(", 1)
        != corrected.read_bytes()
    ):
        raise ValueError("Only the recorded evidence generator-reference repair is accepted")
    repair = proposal.load(out / "evidence-repair.json")
    expected = {
        "operation": "local-evidence-generation-repair-only",
        "original_planning_script_sha256": ORIGINAL_SCRIPT_SHA256,
        "corrected_script_sha256": CORRECTED_SCRIPT_SHA256,
        "saved_plan_sha256": PLAN_SHA256,
        "plan_json_sha256": PLAN_JSON_SHA256,
        "state_sha256": proposal.STATE_SHA256,
        "live_plan_regenerated": False,
        "aws_operations": [],
    }
    if any(repair.get(k) != v for k, v in expected.items()):
        raise ValueError("Explicit evidence-only repair provenance differs")


def validate_plan(plan, prior, old, new):
    proposal.validate_plan(plan, prior, old, new)
    for row in plan["resource_changes"]:
        change = row["change"]
        if row.get("previous_address") or change.get("importing") or change.get("replace_paths"):
            raise ValueError("No resource imports, moves or replacements, including data sources")
        if row.get("mode", "managed") not in ("managed", "data") or (
            row.get("mode") == "data"
            and (
                row["address"] != "data.aws_caller_identity.current"
                or row.get("type") != "aws_caller_identity"
                or row.get("provider_name") != "registry.terraform.io/hashicorp/aws"
                or change["actions"] not in (["read"], ["no-op"])
            )
        ):
            raise ValueError("Unexpected data/config dependency")
    if any(check.get("status") != "pass" for check in plan.get("checks", [])):
        raise ValueError("Plan checks must pass")


def validate_bundle(env, owner, out, execution, recovery, *, applied=False):
    execution.safe_hashes(out, REVIEW_FILES)
    if (
        proposal.sha(out / "review.tfplan") != PLAN_SHA256
        or proposal.sha(out / "plan.json") != PLAN_JSON_SHA256
    ):
        raise ValueError("Existing reviewed binary/JSON digest changed; never replan or replace")
    repair_checks(out, execution)
    record = proposal.load(out / "owner.json")
    expected = {
        "owner_directory": str(owner),
        "lineage": proposal.LINEAGE,
        "serial": proposal.SERIAL,
        "state_sha256": proposal.STATE_SHA256,
        "saved_plan_sha256": PLAN_SHA256,
        "plan_json_sha256": PLAN_JSON_SHA256,
        "granted_resource": proposal.SSM_ARN,
        "creates": 0,
        "changes": 1,
        "deletes": 0,
    }
    if any(record.get(k) != v for k, v in expected.items()):
        raise ValueError("Original plan owner/identity/counts differ")
    hashes = execution.safe_hashes(owner, execution.owner_files(owner))
    if (
        set(record.get("owner_inputs", {})) != set(hashes)
        or record["owner_inputs"]["terraform.tfstate"] != proposal.STATE_SHA256
        or any(
            record["owner_inputs"][k] != v
            for k, v in hashes.items()
            if not (applied and k == "terraform.tfstate")
        )
    ):
        raise ValueError("Original state/source/backend/provider lock/variables differ")
    expected_inputs = {
        proposal.DECLARATION: proposal.sha(ROOT / proposal.DECLARATION),
        PLANNER: ORIGINAL_SCRIPT_SHA256,
    }
    if record.get("proposal_inputs") != expected_inputs:
        raise ValueError("Original exact declaration/planning-source provenance differs")
    pub = owner / "maintenance-reviews" / proposal.PUB_REVIEW
    if (
        record.get("previous_verified_review") != str(pub / proposal.RECEIPT)
        or record.get("previous_review_sha256") != proposal.RECEIPT_SHA256
        or proposal.sha(pub / proposal.RECEIPT) != proposal.RECEIPT_SHA256
    ):
        raise ValueError("Previous verified owner postflight provenance differs")
    execution.verify_manifest(owner, pub, proposal.PUB_MANIFEST, applied=True)
    old, new = proposal.declarations()
    variables = proposal.load(owner / "bootstrap.tfvars.json")
    variables["bootstrap_config_json"] = json.dumps(new)
    if (
        proposal.load(out / "maintenance.tfvars.json") != variables
        or (out / proposal.OVERLAY).read_bytes() != (pub / proposal.OVERLAY).read_bytes()
    ):
        raise ValueError("Saved review variables/additive publisher source differ")
    identity = record.get("identity", {})
    if identity.get("Account") != "835990279085" or not re.fullmatch(
        r"arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_[0-9a-f]+/.+",
        identity.get("Arn", ""),
    ):
        raise ValueError("Original genuine plan must use the restricted owner identity")
    context = proposal.load(out / "context.json")
    if any(
        context.get(k) != v
        for k, v in {
            "component": "identity-center-permission-set",
            "account": "835990279085",
            "region": "us-east-1",
            "profile": "identity-center-plan",
            "synthetic": False,
        }.items()
    ):
        raise ValueError("Original planning context differs")
    evidence = proposal.load(out / "evidence/evidence.json")
    execution.bootstrap.verify_ancestor(evidence.get("repository_commit"))
    if evidence.get("context") != {k: context[k] for k in execution.CONTEXT} or any(
        evidence.get("source", {}).get(k) != v
        for k, v in {
            "synthetic": False,
            "saved_plan_sha256": PLAN_SHA256,
            "plan_json_sha256": PLAN_JSON_SHA256,
        }.items()
    ):
        raise ValueError("Plan/evidence provenance differs")
    plan = execution.maintenance.read_saved_plan(owner, out, env)
    if plan != proposal.load(out / "plan.json"):
        raise ValueError("Saved binary must correspond exactly to the reviewed JSON")
    with zipfile.ZipFile(out / "review.tfplan") as archive:
        names = archive.namelist()
        sources = {"tfconfig/m-/" + p.name: p.read_bytes() for p in owner.glob("*.tf")} | {
            "tfconfig/m-/" + proposal.OVERLAY: (out / proposal.OVERLAY).read_bytes()
        }
        if (
            len(names) != len(set(names))
            or {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            != set(sources)
            or any(archive.read(n) != v for n, v in sources.items())
            or archive.read(".terraform.lock.hcl") != (owner / ".terraform.lock.hcl").read_bytes()
        ):
            raise ValueError("Embedded source/provider lock differs")
        prior = execution.owner_workflow.managed_state(json.loads(archive.read("tfstate-prev")))
    validate_plan(plan, prior, old, new)
    if any(
        {k: v["value"] for k, v in plan.get("variables", {}).items()}.get(k) != v
        for k, v in variables.items()
    ):
        raise ValueError("Saved-plan variables differ")
    if not applied:
        state, managed, _ = proposal.validate_owner(env, execution, recovery)
        if managed != prior:
            raise ValueError("Authoritative current state differs from reviewed before state")
    return plan, prior, old, new


def source_hashes(execution):
    return execution.safe_hashes(ROOT, {proposal.DECLARATION, PLANNER, EXECUTOR})


def history_hashes(execution, owner):
    pub = owner / "maintenance-reviews" / proposal.PUB_REVIEW
    return execution.safe_hashes(
        pub,
        {
            "artifact-publisher-manifest.json",
            "apply.log",
            "apply-result.json",
            "post-apply.json",
            proposal.RECEIPT,
        },
    )


def helper_hashes(execution):
    return execution.safe_hashes(
        proposal.OWNER_REPO,
        execution.PLANNING_INPUTS | {execution.EXECUTOR, "scripts/recheck_artifact_publisher.py"},
    )


def verify_manifest(owner, out, digest, execution, *, applied=False):
    execution.safe_hashes(out, {MANIFEST})
    if not re.fullmatch(r"[0-9a-f]{64}", digest or "") or proposal.sha(out / MANIFEST) != digest:
        raise ValueError("Manifest differs from independently supplied reviewed SHA-256")
    manifest = proposal.load(out / MANIFEST)
    expected = {
        "schema_version": 1,
        "operation": OPERATION,
        "component": "identity-center-permission-set",
        "account": "835990279085",
        "region": "us-east-1",
        "execution_profile": "identity-center-admin",
        "instance_arn": proposal.INSTANCE,
        "owner_directory": str(owner),
        "review_directory": str(out),
        "lineage": proposal.LINEAGE,
        "baseline_serial": proposal.SERIAL,
        "saved_plan_sha256": PLAN_SHA256,
        "plan_json_sha256": PLAN_JSON_SHA256,
        "review_files": execution.safe_hashes(out, REVIEW_FILES),
        "source_inputs": source_hashes(execution),
        "maintenance_helper_inputs": helper_hashes(execution),
        "historical_owner_inputs": history_hashes(execution, owner),
    }
    if (
        any(manifest.get(k) != v for k, v in expected.items())
        or manifest.get("repository", {}).get("name") != "usekarma/aws-iac"
    ):
        raise ValueError("Manifest source/config/plan/identity/provenance changed")
    execution.bootstrap.verify_ancestor(manifest["repository"]["commit"])
    current = execution.safe_hashes(owner, execution.owner_files(owner))
    before = manifest.get("owner_files", {})
    if (
        set(current) != set(before)
        or before["terraform.tfstate"] != proposal.STATE_SHA256
        or any(
            before[k] != v for k, v in current.items() if not (applied and k == "terraform.tfstate")
        )
    ):
        raise ValueError("Sealed state/source/backend/provider-lock/variables changed")
    return manifest


def seal(env, owner_path, review_path):
    env, execution, recovery = guard(env)
    owner, out = review_directory(owner_path, review_path, execution)
    if execution.attempted(out) or (out / MANIFEST).exists() or (out / MANIFEST).is_symlink():
        raise ValueError("Never overwrite/reseal or seal an attempted execution")
    validate_bundle(env, owner, out, execution, recovery)
    identity, snapshot = execution.inventory(env)
    # This also asserts owner caller, both permission sets/policies and all assignments.
    state = proposal.load(owner / "terraform.tfstate")
    old, _ = proposal.declarations()
    execution.require_entry(
        snapshot["permission_sets"][proposal.PS_ARN],
        proposal.PS_ARN,
        old,
        {"623155450153", "835990279085"},
    )
    execution.require_entry(
        snapshot["permission_sets"][proposal.PUB_ARN],
        proposal.PUB_ARN,
        execution.publisher.declaration(),
        {"623155450153"},
    )
    validate_bundle(env, owner, out, execution, recovery)
    manifest = {
        "schema_version": 1,
        "operation": OPERATION,
        "component": "identity-center-permission-set",
        "account": "835990279085",
        "region": "us-east-1",
        "execution_profile": "identity-center-admin",
        "instance_arn": proposal.INSTANCE,
        "owner_directory": str(owner),
        "review_directory": str(out),
        "lineage": state["lineage"],
        "baseline_serial": state["serial"],
        "saved_plan_sha256": PLAN_SHA256,
        "plan_json_sha256": PLAN_JSON_SHA256,
        "repository": {
            "name": "usekarma/aws-iac",
            "commit": execution.bootstrap.git("rev-parse", "HEAD"),
        },
        "owner_files": execution.safe_hashes(owner, execution.owner_files(owner)),
        "review_files": execution.safe_hashes(out, REVIEW_FILES),
        "source_inputs": source_hashes(execution),
        "maintenance_helper_inputs": helper_hashes(execution),
        "historical_owner_inputs": history_hashes(execution, owner),
        "sealing_identity": identity,
        "baseline_inventory": snapshot,
    }
    os.umask(0o077)
    execution.owner_workflow.write(out / MANIFEST, manifest)
    (out / MANIFEST).chmod(0o400)
    digest = proposal.sha(out / MANIFEST)
    print(
        "IoT config-read manifest sealed. Independently record/review SHA-256 before separate apply approval: "
        + digest
    )
    return digest


def planner_probe(env, execution):
    restricted = env | {"AWS_PROFILE": "strall-dev-plan"}
    identity = execution.bootstrap.aws(restricted, "sts", "get-caller-identity")
    if identity.get("Account") != "623155450153" or not re.fullmatch(
        r"arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_IaCPlanReadOnly_[0-9a-f]+/.+",
        identity.get("Arn", ""),
    ):
        raise ValueError("Workload planner probe must use verified strall-dev-plan")
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
            "/iac/iot-digital-twin/core2-aws-001/config",
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
        version = json.loads(result.stdout)
        if type(version) is not int or version < 1:
            raise ValueError("Malformed config parameter version response")
        return {
            "authorized": True,
            "parameter_exists": True,
            "version": version,
            "identity": identity,
        }
    # AWS CLI v2 uses 254 for a service error. Accept only this single error line;
    # a timeout or mixed diagnostics containing old NotFound text is not IAM proof.
    if (
        result.returncode == 254
        and not result.stdout.strip()
        and "AccessDenied" not in result.stderr
        and re.fullmatch(
            r"\s*An error occurred \(ParameterNotFound\) when calling the GetParameter operation"
            r"(?: \(reached max retries: 0\))?(?::[^\r\n]*)?\s*",
            result.stderr,
        )
    ):
        return {
            "authorized": True,
            "parameter_exists": False,
            "result": "ParameterNotFound",
            "identity": identity,
        }
    raise ValueError("Exact config read failed; no permission broadening: " + result.stderr.strip())


def record_postflight(out, result, execution):
    """Never overwrite a historical failure or success when repeating read-only checks."""
    os.umask(0o077)
    original = out / "post-apply.json"
    if original.exists() or original.is_symlink():
        execution.safe_hashes(out, {"post-apply.json"})
        result["previous_postflight_sha256"] = proposal.sha(original)
        base = out / "postflight-rechecks"
        if base.is_symlink():
            raise ValueError("Unsafe postflight receipt directory")
        base.mkdir(mode=0o700, exist_ok=True)
        receipt = Path(tempfile.mkdtemp(prefix="review-", dir=base)) / "postflight.json"
    else:
        receipt = original
    execution.owner_workflow.write(receipt, result)
    return receipt


def postflight(env, owner_path, review_path, digest):
    env, execution, recovery = guard(env)
    owner, out = review_directory(owner_path, review_path, execution)
    manifest = verify_manifest(owner, out, digest, execution, applied=True)
    execution.safe_hashes(out, {"apply.log", "apply-result.json"})
    if proposal.load(out / "apply-result.json") != {
        "operation": OPERATION,
        "manifest_sha256": digest,
        "returncode": 0,
    }:
        raise ValueError("Require recorded successful saved-plan execution; never reapply")
    plan, prior, old, new = validate_bundle(env, owner, out, execution, recovery, applied=True)
    state = proposal.load(owner / "terraform.tfstate")
    if (
        state.get("lineage") != proposal.LINEAGE
        or type(state.get("serial")) is not int
        or state["serial"] <= proposal.SERIAL
    ):
        raise ValueError("Retain same state lineage with an advanced serial")
    managed = execution.owner_workflow.managed_state(state)
    if set(managed) != proposal.EXPECTED or any(
        managed[k] != v for k, v in prior.items() if k != proposal.POLICY
    ):
        raise ValueError(
            "Existing permissions/assignments/publisher state changed or extra resource appeared"
        )
    policy = copy.deepcopy(managed[proposal.POLICY])
    before = copy.deepcopy(prior[proposal.POLICY])
    if (
        json.loads(policy.pop("inline_policy")) != new["inline_policy"]
        or json.loads(before.pop("inline_policy")) != old["inline_policy"]
        or policy != before
    ):
        raise ValueError("Applied IAM delta must be the exact one config ARN only")
    state_hash = proposal.sha(owner / "terraform.tfstate")
    identity, snapshot = execution.inventory(env)
    expected = copy.deepcopy(manifest["baseline_inventory"])
    expected["permission_sets"][proposal.PS_ARN]["inline_policy"] = new["inline_policy"]
    if snapshot != expected:
        raise ValueError(
            "Unrelated Identity Center identity/policy/assignment/managed attachment drift"
        )
    execution.require_entry(
        snapshot["permission_sets"][proposal.PS_ARN],
        proposal.PS_ARN,
        new,
        {"623155450153", "835990279085"},
    )
    probe = planner_probe(env, execution)
    verify_manifest(owner, out, digest, execution, applied=True)
    if proposal.sha(owner / "terraform.tfstate") != state_hash:
        raise ValueError("State changed during read-only postflight")
    result = {
        "status": "verified",
        "operation": OPERATION,
        "manifest_sha256": digest,
        "identity": identity,
        "changed_resource": proposal.POLICY,
        "resource_added": proposal.SSM_ARN,
        "actions_unchanged": True,
        "action_count": 32,
        "conditions_unchanged": True,
        "assignments_unchanged": True,
        "managed_policies_added": [],
        "other_permission_sets_unchanged": True,
        "planner_config_probe": probe,
        "verification_scope": "IAM config-read maintenance only",
        "config_publication_performed": False,
        "ingestion_readiness": "NOT_VERIFIED",
        "lineage": state["lineage"],
        "serial": state["serial"],
        "state_sha256": state_hash,
        "second_state_owner": False,
        "automatic_retry": False,
        "limits": "Point-in-time managed-state and permission-set inventory comparison, not an audit of every external Identity Center operation.",
    }
    receipt = record_postflight(out, result, execution)
    print(
        "STOP_FOR_HUMAN: IAM config-read postflight verified; no config publication or ingestion-readiness assertion. Receipt: "
        + str(receipt)
    )
    return result


def apply(env, owner_path, review_path, digest):
    env, execution, recovery = guard(env, mutation=True)
    owner, out = review_directory(owner_path, review_path, execution)
    if execution.attempted(out):
        raise ValueError("Execution already attempted; no automatic retry/rollback")
    manifest = verify_manifest(owner, out, digest, execution)
    validate_bundle(env, owner, out, execution, recovery)
    _, snapshot = execution.inventory(env)
    if snapshot != manifest["baseline_inventory"]:
        raise ValueError("Live baseline changed since seal; require fresh review")
    verify_manifest(owner, out, digest, execution)
    os.umask(0o077)
    try:
        with (out / "apply.log").open("x") as log:
            result = subprocess.run(
                ["terraform", "apply", "-input=false", "-no-color", str(out / "review.tfplan")],
                cwd=owner,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        execution.owner_workflow.write(
            out / "apply-result.json",
            {"operation": OPERATION, "manifest_sha256": digest, "returncode": result.returncode},
        )
        if result.returncode:
            raise ValueError(
                "Saved-plan apply failed and may be partial; retain state/logs without retry or rollback"
            )
        return postflight(env, owner, out, digest)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as exc:
        record_postflight(
            out,
            {
                "status": "execution-or-postflight-failed-may-be-partial",
                "operation": OPERATION,
                "manifest_sha256": digest,
                "automatic_retry": False,
                "error": str(exc),
            },
            execution,
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "apply", "postflight"])
    parser.add_argument("component", choices=["identity-center-permission-set"])
    parser.add_argument("--owner-dir", required=True)
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action == "seal":
        if args.manifest_sha256:
            parser.error("seal cannot accept an existing digest")
        return seal(dict(os.environ), args.owner_dir, args.review_dir)
    if not args.manifest_sha256:
        parser.error("apply/postflight require independently reviewed --manifest-sha256")
    if args.action == "apply":
        return apply(dict(os.environ), args.owner_dir, args.review_dir, args.manifest_sha256)
    return postflight(dict(os.environ), args.owner_dir, args.review_dir, args.manifest_sha256)


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
