#!/usr/bin/env python3
"""Separate HUMAN-only seal/apply for the reviewed prototype artifact bucket."""

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
from postflight import check_artifact_bucket

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "623155450153"
COMPONENT = "s3-bucket"
NICKNAME = "iot-digital-twin-artifacts"
BUCKET = ACCOUNT + "-iot-digital-twin-artifacts"
CONFIG = "/iac/s3-bucket/iot-digital-twin-artifacts/config"
RUNTIME = "/iac/s3-bucket/iot-digital-twin-artifacts/runtime"
KEY = COMPONENT + "/" + NICKNAME + "/terraform.tfstate"
DECLARATION = "examples/iot-artifact-bucket.strall-dev.json"
DECLARATION_DIGEST = "7b3a15f0bca124878814d5ed692a92f227b2885cca97bb5a8ec7d537b7764b34"
TARGET = {
    "component": COMPONENT,
    "nickname": NICKNAME,
    "account": ACCOUNT,
    "region": "us-east-1",
    "environment": "dev",
    "binding": "strall-com-dev",
    "prefix": "/iac",
}
EXPECTED = {
    "aws_s3_bucket.s3_bucket",
    "aws_s3_bucket_ownership_controls.ownership[0]",
    "aws_s3_bucket_public_access_block.block[0]",
    "aws_s3_bucket_server_side_encryption_configuration.sse[0]",
    "aws_s3_bucket_versioning.versioning",
    "aws_ssm_parameter.runtime",
}
PUBLIC = (
    "block_public_acls",
    "block_public_policy",
    "ignore_public_acls",
    "restrict_public_buckets",
)
INPUTS = {
    DECLARATION,
    "AGENTS.md",
    "terragrunt.hcl",
    "scripts/deploy.sh",
    "scripts/plan.sh",
    "scripts/preflight.sh",
    "scripts/workload_saved_plan.py",
    "scripts/evidence.py",
    "scripts/postflight.py",
} | {"components/s3-bucket/" + n for n in ("header.tf", "main.tf", "outputs.tf")}
REVIEW_FILES = {
    "review.tfplan",
    "plan.json",
    "snapshot.json",
    "context.json",
    "evidence/evidence.json",
    "evidence/summary.md",
}
BACKEND = {
    "bucket": ACCOUNT + "-tf-state",
    "key": KEY,
    "region": "us-east-1",
    "dynamodb_table": ACCOUNT + "-tf-locks",
    "encrypt": True,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2) + "\n")


def declaration():
    value = load(ROOT / DECLARATION)
    digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != DECLARATION_DIGEST:
        raise ValueError("Declaration differs from the exact reviewed prototype config")
    return value


def guard(env, apply=False):
    if env.get("AGENT_MODE") != "0":
        raise ValueError("Human-only workflow requires explicit AGENT_MODE=0; agents cannot use it")
    expected = {
        "AWS_PROFILE": "strall-dev" if apply else "strall-dev-plan",
        "AWS_REGION": "us-east-1",
        "EXPECTED_AWS_ACCOUNT": ACCOUNT,
        "EXPECTED_ENVIRONMENT": "dev",
        "EXPECTED_BINDING": "strall-com-dev",
        "IAC_PREFIX": "/iac",
    }
    if any(env.get(k) != v for k, v in expected.items()):
        raise ValueError(
            "Require the exact reviewed profile/account/region/environment/binding/prefix"
        )
    if apply and env.get("AWS_MUTATION_APPROVED") != "1":
        raise ValueError("Apply additionally requires explicit human AWS_MUTATION_APPROVED=1")
    competing = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_ARN",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "TF_DATA_DIR",
        "TF_WORKSPACE",
        "TF_CLI_CONFIG_FILE",
        "IAC_PREFLIGHT_COMPONENT",
    }
    for name, value in env.items():
        if value and (
            name in competing
            or name.startswith(("TF_VAR_", "TF_CLI_ARGS", "TG_", "TERRAGRUNT_", "AWS_ENDPOINT_URL"))
        ):
            raise ValueError("Unset competing identity/argument override: " + name)
    return env | {
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_MAX_ATTEMPTS": "1",
    }


class ReadError(ValueError):
    pass


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
        raise ReadError("Read-only AWS call failed: " + result.stderr.strip())
    return json.loads(result.stdout or "{}")


def identity(env, restricted):
    result = aws(env, "sts", "get-caller-identity")
    arn = result.get("Arn", "")
    if result.get("Account") != ACCOUNT or not arn.startswith(
        "arn:aws:sts::" + ACCOUNT + ":assumed-role/"
    ):
        raise ValueError("Caller account/assumed role mismatch")
    role = "IaCPlanReadOnly" if restricted else "AdministratorAccess"
    if not re.fullmatch(
        r"arn:aws:sts::" + ACCOUNT + r":assumed-role/AWSReservedSSO_" + role + r"_[0-9a-f]+/.+", arn
    ):
        raise ValueError(
            "Planning requires IaCPlanReadOnly; mutation requires separately verified strall-dev"
        )
    return result


def absent(env, code, operation, *args):
    try:
        aws(env, *operation, *args)
    except ReadError as exc:
        if "(" + code + ") when calling" in str(exc) and "AccessDenied" not in str(exc):
            return
        raise
    raise ValueError("Create-only target already exists: " + operation[1])


def remote_state(env):
    # Read bytes, not Terraform state commands; never initialize/migrate another owner.
    with tempfile.TemporaryDirectory(prefix="workload-state-") as scratch:
        path = Path(scratch) / "state.json"
        try:
            metadata = aws(
                env,
                "s3api",
                "get-object",
                "--bucket",
                BACKEND["bucket"],
                "--key",
                KEY,
                "--expected-bucket-owner",
                ACCOUNT,
                str(path),
            )
        except ReadError as exc:
            if "(NoSuchKey) when calling the GetObject operation" not in str(
                exc
            ) or "AccessDenied" in str(exc):
                raise
            return {"present": False}, None
        state = load(path)
        if not state.get("lineage") or not isinstance(state.get("serial"), int):
            raise ValueError("Remote state has no lineage/serial")
        return {
            "present": True,
            "sha256": sha(path),
            "version_id": metadata.get("VersionId"),
            "etag": metadata.get("ETag"),
            "lineage": state["lineage"],
            "serial": state["serial"],
        }, state


def snapshot(env):
    binding = aws(env, "ssm", "get-parameter", "--name", "/iac/environment")["Parameter"]
    value = json.loads(binding["Value"])
    if (
        binding.get("Name") != "/iac/environment"
        or binding.get("Type") != "String"
        or value.get("name") != TARGET["binding"]
        or value.get("environment") != "dev"
    ):
        raise ValueError("Published environment binding mismatch")
    config = aws(env, "ssm", "get-parameter", "--name", CONFIG)["Parameter"]
    if (
        config.get("Name") != CONFIG
        or config.get("Type") != "String"
        or json.loads(config["Value"]) != declaration()
    ):
        raise ValueError("Published config differs from the reviewed declaration")
    state_identity, state = remote_state(env)
    if state and any(r["mode"] == "managed" for r in state.get("resources", [])):
        raise ValueError("Create-only review requires no pre-existing managed workload state")
    digest = aws(
        env,
        "dynamodb",
        "get-item",
        "--table-name",
        BACKEND["dynamodb_table"],
        "--key",
        json.dumps({"LockID": {"S": BACKEND["bucket"] + "/" + KEY + "-md5"}}),
        "--consistent-read",
    )
    absent(env, "ParameterNotFound", ("ssm", "get-parameter"), "--name", RUNTIME)
    absent(
        env,
        "NoSuchBucket",
        ("s3api", "get-bucket-location"),
        "--bucket",
        BUCKET,
        "--expected-bucket-owner",
        ACCOUNT,
    )
    return {
        "config": {k: config[k] for k in ("Name", "Type", "Version", "Value")},
        "config_sha256": hashlib.sha256(config["Value"].encode()).hexdigest(),
        "binding": {k: binding[k] for k in ("Name", "Type", "Version", "Value")},
        "state": state_identity,
        "state_digest_item": digest,
    }


def safe_files(base, names):
    result = {}
    for name in sorted(names):
        path = base / name
        if (
            not path.is_file()
            or any(p.is_symlink() for p in (path, *path.parents))
            or not path.resolve().is_relative_to(base.resolve())
        ):
            raise ValueError("Missing/unsafe sealed input: " + name)
        result[name] = sha(path)
    return result


def workspace(path):
    raw = Path(path)
    work = raw.resolve(strict=True)
    base = ROOT / ".terragrunt-work" / ACCOUNT / COMPONENT / NICKNAME / ".terragrunt-cache"
    if (
        raw.is_symlink()
        or not work.is_relative_to(base.resolve())
        or work.parts[-2:] != ("components", COMPONENT)
    ):
        raise ValueError("Use only the existing initialized normal workload backend workspace")
    if (work / ".terraform/environment").exists() or (work / "terraform.tfstate").exists():
        raise ValueError("Default remote workspace required; no local/second state owner")
    sources = {p.name for p in work.glob("*.tf")}
    if (
        sources != {"header.tf", "main.tf", "outputs.tf"}
        or list(work.glob("*.tf.json"))
        or list(work.glob("*.tfvars*"))
    ):
        raise ValueError("Unexpected source/variable override in workspace")
    for name in sources:
        if (work / name).read_bytes() != (ROOT / "components" / COMPONENT / name).read_bytes():
            raise ValueError("Workload Terraform source differs from current reviewed source")
    backend = load(work / ".terraform/terraform.tfstate")["backend"]
    config = backend["config"]
    if (
        backend["type"] != "s3"
        or any(config.get(k) != v for k, v in BACKEND.items())
        or any(v is not None for k, v in config.items() if k not in BACKEND)
    ):
        raise ValueError("Backend identity/credentials/override mismatch")
    names = sources | {
        "terragrunt.hcl",
        ".terraform.lock.hcl",
        ".terraform/terraform.tfstate",
        "review.tfplan",
    }
    files = safe_files(work, names)
    # Bind both Terragrunt copies, the original wrapper and the initialized cache.
    wrapper = base.parent / "terragrunt.hcl"
    if (
        wrapper.read_bytes() != (ROOT / "terragrunt.hcl").read_bytes()
        or (work / "terragrunt.hcl").read_bytes() != wrapper.read_bytes()
    ):
        raise ValueError("Terragrunt source differs from reviewed repository")
    files["wrapper"] = sha(wrapper)
    providers = {
        str(p.relative_to(work)): sha(p)
        for p in (work / ".terraform/providers").rglob("terraform-provider-*")
        if p.is_file()
    }
    if not providers:
        raise ValueError("Retain the initialized provider; apply never runs init")
    return (
        work,
        {"files": files, "providers": providers, "terraform": sha(shutil.which("terraform"))},
        config,
    )


def protobuf(data):
    """Read only scalar/bytes wire fields; fail closed on unsupported plan formats."""
    offset = 0

    def varint():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("Invalid saved-plan varint")

    fields = {}
    while offset < len(data):
        key = varint()
        wire = key & 7
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            size = varint() if wire == 2 else {1: 8, 5: 4}[wire]
            value = data[offset : offset + size]
            if len(value) != size:
                raise ValueError("Truncated saved-plan field")
            offset += size
        else:
            raise ValueError("Unsupported saved-plan protobuf field")
        fields.setdefault(key >> 3, []).append(value)
    return fields


def backend_msgpack(value):
    # This deliberately supports only this backend's sorted object, null/string/bool.
    # Terraform plan format v3: planfile.proto Backend.config DynamicValue.msgpack.
    if value is None:
        return b"\xc0"
    if isinstance(value, bool):
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, str):
        data = value.encode()
        prefix = bytes([0xA0 + len(data)]) if len(data) < 32 else b"\xd9" + bytes([len(data)])
        return prefix + data
    if isinstance(value, dict):
        prefix = (
            bytes([0x80 + len(value)])
            if len(value) < 16
            else b"\xde" + len(value).to_bytes(2, "big")
        )
        return prefix + b"".join(
            backend_msgpack(k) + backend_msgpack(v) for k, v in sorted(value.items())
        )
    raise ValueError("Unsupported backend value; separate review required")


def validate_archive(work, binary, backend, live):
    with zipfile.ZipFile(binary) as archive:
        names = archive.namelist()
        sources = {"tfconfig/m-/" + n for n in ("header.tf", "main.tf", "outputs.tf")}
        if (
            len(names) != len(set(names))
            or {n for n in names if n.startswith("tfconfig/") and n.endswith((".tf", ".tf.json"))}
            != sources
        ):
            raise ValueError("Saved-plan source inventory differs")
        for name in sources:
            if archive.read(name) != (work / name.removeprefix("tfconfig/m-/")).read_bytes():
                raise ValueError("Saved plan source differs")
        if archive.read(".terraform.lock.hcl") != (work / ".terraform.lock.hcl").read_bytes():
            raise ValueError("Saved-plan provider lock differs")
        proto = protobuf(archive.read("tfplan"))
        # Pins the supported Terraform format; unknown versions require deliberate review.
        if (
            proto.get(1) != [3]
            or proto.get(14) != [b"1.15.2"]
            or len(proto.get(13, [])) != 1
            or any(proto.get(k) for k in (5, 16, 28, 29, 30, 31, 32))
            or proto.get(17, [0]) != [0]
        ):
            raise ValueError("Unsupported/targeted/action/destroy saved plan")
        be = protobuf(proto[13][0])
        if (
            be.get(1) != [b"s3"]
            or be.get(3) != [b"default"]
            or len(be.get(2, [])) != 1
            or protobuf(be[2][0]).get(1) != [backend_msgpack(backend)]
        ):
            raise ValueError("Binary saved-plan backend differs from initialized owner")
        state = json.loads(archive.read("tfstate"))
        previous = json.loads(archive.read("tfstate-prev"))
        if any(r["mode"] == "managed" for s in (state, previous) for r in s.get("resources", [])):
            raise ValueError("Saved plan has a pre-existing managed state owner")
        data = state.get("resources", [])
        if (
            len(data) != 1
            or data[0].get("mode") != "data"
            or data[0].get("type") != "aws_ssm_parameter"
            or data[0].get("name") != "config"
            or len(data[0]["instances"]) != 1
        ):
            raise ValueError("Require the normal published SSM config snapshot")
        attributes = data[0]["instances"][0]["attributes"]
        if any(
            attributes.get(k) != live["config"][v]
            for k, v in {
                "name": "Name",
                "type": "Type",
                "version": "Version",
                "value": "Value",
            }.items()
        ):
            raise ValueError("Published SSM config changed since planning")


def validate_plan(plan):
    if (
        plan.get("complete") is not True
        or plan.get("errored")
        or plan.get("resource_drift")
        or plan.get("deferred_changes")
        or plan.get("action_invocations")
    ):
        raise ValueError("Incomplete/errored/drifting/action plan")
    variables = {k: v["value"] for k, v in plan["variables"].items()}
    if variables != {
        "component_name": COMPONENT,
        "nickname": NICKNAME,
        "region": "us-east-1",
        "iac_prefix": "/iac",
        "plan_config_json": None,
    }:
        raise ValueError("Only normal SSM-backed plan variables are eligible")
    resources = plan["resource_changes"]
    if len(resources) != 6 or {r["address"] for r in resources} != EXPECTED:
        raise ValueError("Require exactly the reviewed six creates")
    after = {}
    for resource in resources:
        change = resource["change"]
        if (
            resource.get("mode") != "managed"
            or resource.get("provider_name") != "registry.terraform.io/hashicorp/aws"
            or resource.get("type") != resource["address"].split(".")[0]
            or change["actions"] != ["create"]
            or change.get("before") is not None
            or change.get("importing")
            or change.get("replace_paths")
        ):
            raise ValueError("Unexpected provider/action/import/replacement")
        after[resource["address"]] = change["after"]
    bucket = after["aws_s3_bucket.s3_bucket"]
    tags = declaration()["tags"] | {"Component": COMPONENT}
    if (
        bucket.get("bucket") != BUCKET
        or bucket.get("force_destroy") is not False
        or bucket.get("tags") != tags
        or any(
            bucket.get(k)
            for k in (
                "website",
                "policy",
                "lifecycle_rule",
                "cors_rule",
                "logging",
                "replication_configuration",
            )
        )
    ):
        raise ValueError("Bucket identity/security/tags differs")
    if after["aws_s3_bucket_versioning.versioning"].get("versioning_configuration") != [
        {"status": "Enabled"}
    ] or after["aws_s3_bucket_ownership_controls.ownership[0]"].get("rule") != [
        {"object_ownership": "BucketOwnerEnforced"}
    ]:
        raise ValueError("Versioning/ownership differs")
    if any(after["aws_s3_bucket_public_access_block.block[0]"].get(k) is not True for k in PUBLIC):
        raise ValueError("Public access block differs")
    encryption = after["aws_s3_bucket_server_side_encryption_configuration.sse[0]"]
    if encryption.get("bucket") != BUCKET or encryption.get("rule") != [
        {"apply_server_side_encryption_by_default": [{"sse_algorithm": "AES256"}]}
    ]:
        raise ValueError("Encryption differs")
    runtime = after["aws_ssm_parameter.runtime"]
    if (
        runtime.get("name") != RUNTIME
        or runtime.get("type") != "String"
        or json.loads(runtime["value"]) != {"bucket_name": BUCKET}
    ):
        raise ValueError("Runtime parameter differs")


def read_plan(work, binary, env):
    result = subprocess.run(
        ["terraform", "show", "-json", str(binary)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("Saved-plan export failed; no mutation allowed")
    return json.loads(result.stdout)


def reader(env):
    return env | {"AWS_PROFILE": "strall-dev-plan"}


def preflight(env):
    identity(env, True)
    subprocess.run(["bash", str(ROOT / "scripts/preflight.sh")], cwd=ROOT, env=env, check=True)


def seal(env, plan_dir):
    env = guard(env)
    os.umask(0o077)
    preflight(env)
    work, inputs, backend = workspace(plan_dir)
    live = snapshot(env)
    plan = read_plan(work, work / "review.tfplan", env)
    validate_plan(plan)
    validate_archive(work, work / "review.tfplan", backend, live)
    base = ROOT / "artifacts/workload-saved-plan"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    out = Path(tempfile.mkdtemp(prefix="review-", dir=base))
    shutil.copyfile(work / "review.tfplan", out / "review.tfplan")
    write(out / "plan.json", plan)
    write(out / "snapshot.json", live)
    context = TARGET | {
        "objective": "Human saved-plan artifact-bucket execution review",
        "repositories": ["aws-iac", "aws-config"],
        "files": sorted(INPUTS),
        "profile": "strall-dev-plan",
        "configuration_changes": "Exact published SSM config; no override/publication",
        "validation_results": {"plan": "6 creates, 0 changes, 0 deletes; exact bucket controls"},
        "blast_radius": "Six reviewed resources in existing normal S3 state owner",
        "recovery": "Retain state/logs; fresh human recovery review after partial failure, no automatic retry/rollback",
        "post_change_checks": [
            "Exact bucket security, runtime, restricted runtime read and managed-state scope"
        ],
        "synthetic": False,
    }
    write(out / "context.json", context)
    generate(out / "plan.json", out / "context.json", out / "evidence", out / "review.tfplan")
    # Catch concurrent input changes before sealing. Never silently reseal.
    if (
        workspace(work)[1] != inputs
        or snapshot(env) != live
        or sha(out / "review.tfplan") != sha(work / "review.tfplan")
    ):
        raise ValueError("Inputs changed during seal; retain failed bundle and obtain a new review")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = TARGET | {
        "schema_version": 1,
        "workspace": str(work),
        "review_directory": str(out),
        "repository_commit": commit,
        "workspace_inputs": inputs,
        "repository_inputs": safe_files(ROOT, INPUTS),
        "review_files": safe_files(out, REVIEW_FILES),
    }
    write(out / "manifest.json", manifest)
    (out / "manifest.json").chmod(0o400)
    print("STOP_FOR_HUMAN: private review bundle: " + str(out))
    print("Independently record/review manifest SHA-256: " + sha(out / "manifest.json"))
    return out


def verify_manifest(out, digest):
    out = Path(out).resolve(strict=True)
    if out.parent != (ROOT / "artifacts/workload-saved-plan").resolve() or not out.name.startswith(
        "review-"
    ):
        raise ValueError("Use the private workload review bundle in this repository")
    safe_files(out, REVIEW_FILES | {"manifest.json"})
    if not re.fullmatch(r"[0-9a-f]{64}", digest or "") or sha(out / "manifest.json") != digest:
        raise ValueError("Independently reviewed manifest digest mismatch")
    manifest = load(out / "manifest.json")
    if (
        any(manifest.get(k) != v for k, v in TARGET.items())
        or manifest.get("schema_version") != 1
        or manifest.get("review_directory") != str(out)
    ):
        raise ValueError("Sealed target mismatch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", manifest["repository_commit"], "HEAD"],
        cwd=ROOT,
        check=True,
    )
    if manifest.get("repository_inputs") != safe_files(ROOT, INPUTS) or manifest.get(
        "review_files"
    ) != safe_files(out, REVIEW_FILES):
        raise ValueError("Sealed source/declaration/plan/JSON changed")
    work, inputs, backend = workspace(manifest["workspace"])
    if inputs != manifest.get("workspace_inputs") or sha(out / "review.tfplan") != sha(
        work / "review.tfplan"
    ):
        raise ValueError("Sealed workspace/backend/provider lock/plan changed")
    return work, out, backend


def postflight(env):
    restricted = reader(env)
    identity(restricted, True)
    check_artifact_bucket(lambda *args: aws(restricted, *args))
    state_identity, state = remote_state(restricted)
    managed = set()
    count = 0
    for resource in (state or {}).get("resources", []):
        if resource["mode"] != "managed":
            continue
        for instance in resource["instances"]:
            if resource.get("module") or instance.get("deposed"):
                raise ValueError("Unexpected postflight managed-state instance")
            count += 1
            address = resource["type"] + "." + resource["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"]) + "]"
            managed.add(address)
    if count != 6 or managed != EXPECTED:
        raise ValueError("Postflight managed-state scope differs from six reviewed resources")
    return {
        "status": "verified",
        "bucket": BUCKET,
        "runtime": RUNTIME,
        "restricted_runtime_read": True,
        "managed_resources": sorted(managed),
        "state": state_identity,
    }


def apply_saved(env, review_dir, digest):
    env = guard(env, apply=True)
    os.umask(0o077)
    work, out, backend = verify_manifest(review_dir, digest)
    if (out / "apply.log").exists() or (out / "post-apply.json").exists():
        raise ValueError("Execution already attempted; never automatically retry/rollback")
    caller = identity(env, False)  # Separate human write profile, exact workload account.
    readonly = reader(env)
    preflight(readonly)
    live = snapshot(readonly)
    if live != load(out / "snapshot.json"):
        raise ValueError("Published config/binding/remote state changed after seal")
    plan = read_plan(work, out / "review.tfplan", readonly)
    if plan != load(out / "plan.json"):
        raise ValueError("Saved binary plan no longer corresponds to reviewed JSON")
    validate_plan(plan)
    validate_archive(work, out / "review.tfplan", backend, live)
    if snapshot(readonly) != live:
        raise ValueError("Remote inputs changed before execution")
    verify_manifest(out, digest)
    if identity(env, False) != caller:
        raise ValueError("Human write identity changed before execution")
    # The exclusive log is an attempt marker. No init, replan, Terragrunt or retry.
    record = {
        "status": "apply-failed-may-be-partial",
        "manifest_sha256": digest,
        "caller": caller,
        "automatic_retry": False,
    }
    with (out / "apply.log").open("x") as log:
        try:
            result = subprocess.run(
                ["terraform", "apply", "-input=false", "-no-color", str(out / "review.tfplan")],
                cwd=work,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                raise ValueError(
                    "Apply failed and may be partial; retain logs/state, no automatic retry/rollback"
                )
            record["status"] = "postflight-failed"
            record.update(postflight(env))
        finally:
            write(out / "post-apply.json", record)
    print(
        "Human exact saved-plan apply and read-only postflight verified; retain remote state/logs"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "apply"])
    parser.add_argument("component", choices=[COMPONENT])
    parser.add_argument("nickname", choices=[NICKNAME])
    parser.add_argument("--plan-dir")
    parser.add_argument("--review-dir")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action == "seal":
        if not args.plan_dir or args.review_dir or args.manifest_sha256:
            parser.error("seal requires only --plan-dir, using the existing normal plan")
        seal(dict(os.environ), args.plan_dir)
    else:
        if args.plan_dir or not args.review_dir or not args.manifest_sha256:
            parser.error("apply requires --review-dir and independently recorded --manifest-sha256")
        apply_saved(dict(os.environ), args.review_dir, args.manifest_sha256)


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        IndexError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as exc:
        print("STOP_FOR_HUMAN: " + str(exc), file=sys.stderr)
        sys.exit(1)
