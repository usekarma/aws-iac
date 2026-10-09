#!/usr/bin/env python3
"""Bounded local role handoff and verification; never executes AWS operations."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("architect", "builder", "verifier", "reviewer", "security", "operations")
REVIEWS = ("reviewer", "security", "operations")
RISKS = ("delete", "replacement", "state_change", "iam_change", "network_exposure", "cost_change")


def load(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args, directory=ROOT):
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True).strip()


def local_path(value):
    path = Path(value)
    if (
        not isinstance(value, str)
        or not value
        or path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or path.parts[0] == ".git"
    ):
        raise ValueError("Expected repository-relative path")
    return path


def strings(value):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError("Expected list of nonempty strings")
    return value


def validate(request, evaluation=False):
    expected = {
        "schema_version",
        "id",
        "components",
        "desired_state",
        "authorization_reference",
        "allowed_paths",
        "architect",
        "builder",
        "reviews",
    }
    if set(request) != expected or request["schema_version"] != 1:
        raise ValueError(
            "Unsupported request fields/version; no command hooks or AWS targeting supported"
        )
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", request["id"]):
        raise ValueError("Invalid request identifier")
    for key in ("authorization_reference",):
        if not isinstance(request[key], str) or not request[key].strip():
            raise ValueError("Missing human work-request reference")
    components = strings(request["components"])
    if not components or len(components) != len(set(components)):
        raise ValueError("Expected distinct affected components")
    for component in components:
        if (
            not re.fullmatch(r"[a-z0-9-]+", component)
            or not (ROOT / "components" / component / "header.tf").is_file()
        ):
            raise ValueError("Unknown component; deployability is checked by existing verification")
    paths = strings(request["allowed_paths"])
    if not paths and not evaluation:
        raise ValueError("Missing authorized repository scope")
    for path in paths:
        local_path(path)
    desired = request["desired_state"]
    if set(desired) != {"repository", "config_paths"}:
        raise ValueError("Expected explicit desired-state repository/config paths")
    if evaluation and desired["repository"] is None:
        if desired["config_paths"]:
            raise ValueError("Config paths require an explicit desired-state repository")
        repository = None
    else:
        repository = (ROOT / desired["repository"]).resolve()
    for path in strings(desired["config_paths"]):
        relative = local_path(path)
        source = (repository / relative).resolve()
        if not source.is_relative_to(repository) or not source.is_file():
            raise ValueError("Missing or escaping desired-state source")
    if not desired["config_paths"] and not evaluation:
        raise ValueError("Missing desired-state sources")
    architect = request["architect"]
    if (
        set(architect) != {"plan", "risk_flags", "assumptions", "required_human_decisions"}
        or not isinstance(architect["plan"], str)
        or not architect["plan"].strip()
    ):
        raise ValueError("Missing Architect plan")
    if set(architect["risk_flags"]) != set(RISKS) or any(
        v not in ("yes", "no", "unknown") for v in architect["risk_flags"].values()
    ):
        raise ValueError("Every risk must explicitly be yes/no/unknown")
    strings(architect["assumptions"])
    strings(architect["required_human_decisions"])
    builder = request["builder"]
    if not evaluation and (
        set(builder) != {"complete", "summary"}
        or type(builder["complete"]) is not bool
        or not isinstance(builder["summary"], str)
    ):
        raise ValueError("Invalid Builder report")
    if evaluation and (builder is not None or paths):
        raise ValueError("Evaluation cannot invoke Builder or authorize repository edits")
    if set(request["reviews"]) != set(REVIEWS):
        raise ValueError("Expected Reviewer, Security and Operations reports")
    for review in request["reviews"].values():
        if set(review) != {"summary", "findings", "blocking_findings"} or not isinstance(
            review["summary"], str
        ):
            raise ValueError("Invalid role report")
        strings(review["findings"])
        strings(review["blocking_findings"])
    return repository


def snapshot(request, repository):
    base = os.environ.get("VERIFY_BASE_REF", "origin/main")
    git("rev-parse", "--verify", base)
    names = set(git("diff", "--name-only", f"{base}...HEAD").splitlines())
    names.update(git("diff", "--name-only", "HEAD").splitlines())
    names.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    files = {
        name: digest(ROOT / name) if (ROOT / name).is_file() else "deleted"
        for name in sorted(names)
    }
    return {
        "iac_commit": git("rev-parse", "HEAD"),
        "verification_base": base,
        "desired_state_commit": git("rev-parse", "HEAD", directory=repository)
        if repository
        else None,
        "desired_state_files": {
            name: digest(repository / name) for name in request["desired_state"]["config_paths"]
        },
        "config_contract_sha256": digest(repository / "contracts/config-contract.json")
        if repository and (repository / "contracts/config-contract.json").is_file()
        else None,
        "component_files": {
            str(path.relative_to(ROOT)): digest(path)
            for component in request["components"]
            for path in sorted((ROOT / "components" / component).rglob("*"))
            if path.is_file()
            and not any(part in (".terraform", "__pycache__") for part in path.parts)
            and not path.name.endswith((".tfstate", ".tfstate.backup"))
        },
        "files_changed": files,
    }


def isolated_environment(home, repository):
    # No inherited approvals, AWS profiles/credentials, Terraform CLI injection,
    # backend bootstrap flags or metadata/container credential sources.
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "AGENT_MODE": "1",
        "PYTHONPATH": str(ROOT / "scripts"),
        **({"AWS_CONFIG_DIR": str(repository)} if repository else {}),
        "AWS_CONFIG_FILE": str(home / "aws-config"),
        "AWS_SHARED_CREDENTIALS_FILE": str(home / "aws-credentials"),
        "AWS_EC2_METADATA_DISABLED": "true",
        "TF_IN_AUTOMATION": "true",
        "VERIFY_BASE_REF": os.environ.get("VERIFY_BASE_REF", "origin/main"),
    }


def gate_commands(request, repository):
    # --terraform already includes every repository gate and test. Do not add
    # a standalone verify/test run here or reimplement provider validation.
    compatibility = (
        [
            (
                "config_compatibility",
                [
                    sys.executable,
                    "scripts/check_config_contract.py",
                    "--aws-config-dir",
                    str(repository),
                ],
            )
        ]
        if repository
        else []
    )
    return compatibility + [
        ("module_" + component, ["bash", "scripts/verify.sh", "--terraform", component])
        for component in request["components"]
    ]


def run_gates(request, repository, output):
    results = []
    with tempfile.TemporaryDirectory(prefix="agent-gates-") as temporary:
        env = isolated_environment(Path(temporary), repository)
        for name, command in gate_commands(request, repository):
            log = output / (name + ".log")
            try:
                with log.open("w") as stream:
                    result = subprocess.run(
                        command,
                        cwd=ROOT,
                        env=env,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        timeout=1200,
                        check=False,
                    )
                code, status = result.returncode, "PASS" if result.returncode == 0 else "FAIL"
            except (OSError, subprocess.TimeoutExpired):
                code, status = None, "ERROR"
            results.append(
                {
                    "name": name,
                    "command": command,
                    "status": status,
                    "returncode": code,
                    "evidence_kind": "local_static",
                    "log": log.name,
                }
            )
    if repository is None:
        results.insert(
            0,
            {
                "name": "config_compatibility",
                "command": None,
                "status": "NOT_AVAILABLE",
                "returncode": None,
                "evidence_kind": "local_static",
                "log": None,
            },
        )
    return results


def identity_fields(request):
    return {
        k: request[k]
        for k in ("id", "components", "desired_state", "authorization_reference", "allowed_paths")
    }


def assemble(request, before, after, checks, cycle, evaluation=False):
    blockers = []
    if evaluation and not request["desired_state"]["config_paths"]:
        blockers.append("Desired-state configuration sources not supplied; alignment is unverified")
    if not evaluation and (
        not request["builder"]["complete"] or not request["builder"]["summary"].strip()
    ):
        blockers.append("Builder implementation is incomplete")
    for name in [] if evaluation else before["files_changed"]:
        if not any(
            name == scope or (scope.endswith("/") and name.startswith(scope))
            for scope in request["allowed_paths"]
        ):
            blockers.append("Changed file outside authorized scope: " + name)
    if before != after:
        blockers.append(
            "Repository/desired-state snapshot changed during verification; evidence is stale"
        )
    for check in checks:
        if check["status"] != "PASS":
            blockers.append("Verification failed: " + check["name"])
    expected_checks = {"config_compatibility"} | {"module_" + c for c in request["components"]}
    if {c["name"] for c in checks} != expected_checks or len(checks) != len(expected_checks):
        blockers.append("Required verification evidence is incomplete or duplicated")
    for role, review in request["reviews"].items():
        if not review["summary"].strip():
            blockers.append("Missing assessment: " + role)
        blockers.extend(role + ": " + finding for finding in review["blocking_findings"])
    trace = [
        {"stage": role, "cycle": cycle} for role in ROLES if not evaluation or role != "builder"
    ]
    if cycle:
        trace.insert(0, {"stage": "ONE_REMEDIATION_PASS", "cycle": cycle})
    trace.append({"stage": "STOP_FOR_HUMAN", "cycle": cycle})
    return {
        "schema_version": 1,
        "mode": "EVALUATION_ONLY" if evaluation else "IMPLEMENTATION",
        "work_request_id": request["id"],
        "cycle": cycle,
        "identity_fields": identity_fields(request),
        "snapshot": before,
        "affected_components": request["components"],
        "desired_state_source": request["desired_state"],
        "architect_plan": request["architect"],
        "builder_report": request["builder"],
        "checks": checks,
        "terraform_terragrunt_validation": {
            c["name"]: c["status"] for c in checks if c["name"].startswith("module_")
        },
        "role_assessments": request["reviews"],
        "plan_evidence": {"status": "NOT_PRODUCED"},
        "live_aws_evidence": {"status": "NOT_COLLECTED"},
        "risk_flags": request["architect"]["risk_flags"],
        "unresolved_blockers": blockers,
        "required_human_decisions": request["architect"]["required_human_decisions"],
        "transitions": trace,
        "final_state": "BLOCKED" if blockers else "READY_FOR_HUMAN_REVIEW",
        "stop": "STOP_FOR_HUMAN",
        "remediation_remaining": 1 - cycle if blockers and not evaluation else 0,
        "limitations": [
            "Role reports and authorization references are supplied, not independently attested.",
            "Local validation is not a live plan, AWS evidence or deployment approval.",
            "Runner executes fixed gates only; repository edits and semantic reviews occur in separately authorized sessions.",
        ],
    }


def write_evidence(output, request, evidence):
    (output / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")

    def text(value):
        return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")

    def bullets(items, empty="None reported"):
        return ["- " + text(item) for item in items] or [empty]

    source = evidence["desired_state_source"]
    lines = [
        "# Bounded agent workflow",
        "",
        f"Request: {evidence['work_request_id']}",
        f"Mode: {evidence['mode']}",
        "Components: " + ", ".join(evidence["affected_components"]),
        f"Final state: **{evidence['final_state']}** — STOP_FOR_HUMAN",
        "",
        "Local/static evidence only. Plan: NOT_PRODUCED. Live AWS: NOT_COLLECTED.",
        "Builder: "
        + (
            "NOT_INVOKED; no remediation available."
            if evidence["mode"] == "EVALUATION_ONLY"
            else "Supplied implementation report; one continuation maximum."
        ),
        "",
        "## Desired-state source",
        "",
        "Repository: " + text(source["repository"] or "NOT_AVAILABLE — no source supplied"),
        "Revision: " + text(evidence["snapshot"]["desired_state_commit"] or "NOT_AVAILABLE"),
    ]
    lines += bullets(
        source["config_paths"],
        "No configuration files supplied; configuration alignment is not established.",
    )
    lines += [
        "",
        "## Checks run",
        "",
        "Each module check delegates to verify.sh --terraform: repository formatting/lint, tests, static security, Terraform fmt, Terragrunt HCL validation, then backend-disabled provider validation.",
        "",
        "| Check | Command | Result | Log |",
        "| --- | --- | --- | --- |",
    ]
    for check in evidence["checks"]:
        command = (
            shlex.join(check["command"]) if check["command"] else "Not run: source unavailable"
        )
        log = f"[{check['log']}]({check['log']})" if check["log"] else "None"
        lines.append(f"| {check['name']} | {text(command)} | {check['status']} | {log} |")
    lines += [
        "",
        "## Architect assessment",
        "",
        text(evidence["architect_plan"]["plan"]),
        "",
        "Assumptions:",
        "",
    ]
    lines += bullets(evidence["architect_plan"]["assumptions"])
    lines += [
        "",
        "## Destructive/replacement and other risks",
        "",
        "Supplied static assessment; live actions remain unverified without a reviewed plan.",
        "",
        "| Risk | Assessment |",
        "| --- | --- |",
    ]
    lines += [f"| {key} | {value} |" for key, value in evidence["risk_flags"].items()]
    for role, title in [
        ("reviewer", "Repository/convention findings"),
        ("security", "Security findings"),
        ("operations", "Operations, cost and persistence findings"),
    ]:
        assessment = evidence["role_assessments"][role]
        lines += [
            "",
            "## " + title,
            "",
            "Supplied role assessment: " + text(assessment["summary"] or "MISSING"),
            "",
        ]
        lines += bullets(assessment["findings"])
        if assessment["blocking_findings"]:
            lines += ["", "Blocking findings:", ""] + bullets(assessment["blocking_findings"])
    lines += ["", "## Unresolved blockers", ""] + bullets(evidence["unresolved_blockers"])
    lines += ["", "## Required human decisions", ""] + bullets(evidence["required_human_decisions"])
    lines += [
        "",
        "## Source and diff provenance",
        "",
        "Source/diff fingerprints are recorded in evidence.json; supplied reviews are not independently attested.",
        "Changed repository files (observation only in evaluation mode):",
        "",
    ]
    lines += bullets(evidence["snapshot"]["files_changed"], "No changed repository files observed.")
    lines += ["", "## Limitations", ""] + bullets(evidence["limitations"])
    (output / "report.md").write_text("\n".join(lines) + "\n")
    (output / "manifest.json").write_text(
        json.dumps({p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}, indent=2)
        + "\n"
    )


def evaluation_request(component, repository=None, config_paths=None, assessment=None):
    report = (
        load(assessment)
        if assessment
        else {
            "architect": {
                "plan": "Evaluate existing component using repository-owned gates; do not implement or remediate.",
                "risk_flags": {key: "unknown" for key in RISKS},
                "assumptions": [
                    "No AWS target selected; local validation cannot determine live resource actions."
                ],
                "required_human_decisions": [
                    "Obtain semantic security/operations review and confirm desired state before any separately requested live plan."
                ],
            },
            "reviews": {
                role: {"summary": "", "findings": [], "blocking_findings": []} for role in REVIEWS
            },
        }
    )
    if set(report) != {"architect", "reviews"}:
        raise ValueError("Evaluation assessment must contain only architect/reviews")
    return {
        "schema_version": 1,
        "id": "evaluation-" + component,
        "components": [component],
        "desired_state": {
            "repository": str(repository) if repository else None,
            "config_paths": config_paths or [],
        },
        "authorization_reference": "Explicit evaluation-only invocation; no implementation or AWS authorization",
        "allowed_paths": [],
        "builder": None,
        **report,
    }


def execute(request_path, output_path=None, remediate=False, evaluation=False):
    if evaluation and remediate:
        raise ValueError("Evaluation-only mode cannot remediate")
    os.environ["AGENT_MODE"] = "1"
    os.umask(0o077)
    request = request_path if isinstance(request_path, dict) else load(request_path)
    repository = validate(request, evaluation=evaluation)
    output = Path(output_path or ROOT / "artifacts/agent-workflow" / request["id"]).resolve()
    if not output.is_relative_to((ROOT / "artifacts/agent-workflow").resolve()):
        raise ValueError("Evidence must be under ignored artifacts/agent-workflow/")
    cycle = 0
    if remediate:
        previous_dir = output / "cycle-0"
        previous = load(previous_dir / "evidence.json")
        manifest = load(previous_dir / "manifest.json")
        if not {"evidence.json", "request.json", "report.md"}.issubset(manifest) or any(
            Path(name).name != name for name in manifest
        ):
            raise ValueError("Invalid previous evidence manifest")
        if any(digest(previous_dir / name) != value for name, value in manifest.items()):
            raise ValueError("Previous evidence integrity check failed")
        if (
            previous.get("mode", "IMPLEMENTATION") != "IMPLEMENTATION"
            or previous["final_state"] != "BLOCKED"
            or previous["cycle"] != 0
            or previous["identity_fields"] != identity_fields(request)
        ):
            raise ValueError("Remediation requires same blocked work request and approved scope")
        if previous["snapshot"]["desired_state_files"] != {
            name: digest(repository / name) for name in request["desired_state"]["config_paths"]
        }:
            raise ValueError("Desired state changed; obtain a new reviewed work request")
        if previous["snapshot"]["desired_state_commit"] != git(
            "rev-parse", "HEAD", directory=repository
        ) or previous["snapshot"]["config_contract_sha256"] != digest(
            repository / "contracts/config-contract.json"
        ):
            raise ValueError("Desired-state revision/contract changed")
        cycle = 1
    else:
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
    cycle_dir = output / f"cycle-{cycle}"
    cycle_dir.mkdir(mode=0o700, exist_ok=False)
    before = snapshot(request, repository)
    checks = run_gates(request, repository, cycle_dir)
    evidence = assemble(
        request, before, snapshot(request, repository), checks, cycle, evaluation=evaluation
    )
    write_evidence(cycle_dir, request, evidence)
    print(evidence["final_state"] + ": STOP_FOR_HUMAN; private evidence saved.")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?")
    parser.add_argument(
        "--evaluate",
        metavar="COMPONENT",
        help="Evaluate existing component without Builder or remediation",
    )
    parser.add_argument(
        "--aws-config-dir", type=Path, help="Explicit desired-state checkout for evaluation"
    )
    parser.add_argument(
        "--config-path",
        action="append",
        default=[],
        help="Desired-state file relative to explicit checkout; repeatable",
    )
    parser.add_argument(
        "--assessment",
        type=Path,
        help="Supplied Architect/Reviewer/Security/Operations assessment for evaluation",
    )
    parser.add_argument("--output", type=Path, help="NEW directory under artifacts/agent-workflow/")
    parser.add_argument(
        "--remediate",
        action="store_true",
        help="One continuation after externally applied repository fixes/fresh reviews",
    )
    args = parser.parse_args()
    if args.evaluate:
        if args.request or args.remediate:
            raise ValueError("Evaluation cannot use implementation requests or remediation")
        request = evaluation_request(
            args.evaluate, args.aws_config_dir, args.config_path, args.assessment
        )
        evidence = execute(request, args.output, evaluation=True)
    else:
        if not args.request or args.aws_config_dir or args.config_path or args.assessment:
            raise ValueError("Use an implementation request or explicit --evaluate mode")
        evidence = execute(args.request, args.output, args.remediate)
    return 2 if evidence["final_state"] == "BLOCKED" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print(
            "Workflow stopped: invalid input, exhausted cycle or unavailable source/gate. No cloud operations performed; details withheld.",
            file=sys.stderr,
        )
        sys.exit(1)
