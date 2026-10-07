#!/usr/bin/env python3
"""Non-destructive repository checks. No AWS calls or remote backend initialization."""

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def run(args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    subprocess.run(args, check=True, **kwargs)


def git_paths(*args):
    return set(subprocess.check_output(["git", *args], text=True).splitlines())


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: " + key)
        value[key] = item
    return value


def load_json(path):
    return json.loads(
        path.read_text(),
        object_pairs_hook=no_duplicates,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("invalid JSON number " + x)),
    )


def validate_config(path, value):
    if path.parts[0] not in ("iac", "account_environments"):
        return
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{path}: expected non-empty JSON object")
    if path.parts[0] == "account_environments":
        required = ("name", "environment", "config_repo", "config_branch", "iac_repo", "iac_branch")
        for key in required:
            if not isinstance(value.get(key), str) or not value[key]:
                raise ValueError(f"{path}: missing/non-string {key}")
        if value["name"] != path.stem or not (ROOT / "iac" / value["environment"]).is_dir():
            raise ValueError(f"{path}: binding name/environment does not match repository")
        for key in ("iac_strict", "lambda_strict", "allow_drift"):
            if key in value and not isinstance(value[key], bool):
                raise ValueError(f"{path}: {key} must be boolean")
    else:
        if len(path.parts) != 5 or path.name != "config.json":
            raise ValueError(f"{path}: expected iac/environment/component/nickname/config.json")
        if "tags" in value and (
            not isinstance(value["tags"], dict)
            or any(not isinstance(v, str) for v in value["tags"].values())
        ):
            raise ValueError(f"{path}: tags must map strings to strings")
        if "AWS_IAC_DIR" in os.environ:
            component = Path(os.environ["AWS_IAC_DIR"]) / "components" / path.parts[2]
            if not component.is_dir():
                raise ValueError(f"{path}: unknown sibling IaC component")


def provider_validate(component):
    modules = (
        sorted((ROOT / "components").iterdir())
        if component == "all"
        else [ROOT / "components" / component]
    )
    if not re.fullmatch(r"[a-z0-9-]+", component):
        raise ValueError("Invalid component")
    status = (
        load_json(ROOT / "components/status.json")
        if (ROOT / "components/status.json").exists()
        else {}
    )
    for module in modules:
        if status.get(module.name, {}).get("status") == "incomplete":
            raise ValueError("Incomplete component is blocked: " + module.name)
        if not module.is_dir() or not list(module.glob("*.tf")):
            if component == "all":
                continue
            raise ValueError("No Terraform module: " + component)
        with tempfile.TemporaryDirectory(prefix="iac-validate-") as scratch:
            shutil.copytree(
                module,
                scratch,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".terraform", "*.tfstate", "*.tfstate.*"),
            )
            env = os.environ.copy()
            for key in list(env):
                if key.startswith("TF_CLI_ARGS"):
                    del env[key]
            env.update(
                AWS_EC2_METADATA_DISABLED="true",
                TF_IN_AUTOMATION="true",
                TF_DATA_DIR=str(Path(scratch) / ".terraform"),
            )
            run(
                ["terraform", "init", "-backend=false", "-input=false", "-no-color"],
                cwd=scratch,
                env=env,
            )
            run(["terraform", "validate", "-no-color"], cwd=scratch, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--terraform",
        metavar="COMPONENT",
        help="provider validation in a disposable copy; use all for all modules",
    )
    parser.add_argument(
        "--terraform-changed",
        action="store_true",
        help="backend-disabled provider validation of modules affected by the diff",
    )
    args = parser.parse_args()
    base = os.environ.get("VERIFY_BASE_REF", "origin/main")
    run(["git", "rev-parse", "--verify", base])
    files = git_paths("ls-files") | git_paths("ls-files", "--others", "--exclude-standard")
    changed = (
        git_paths("diff", "--name-only", f"{base}...HEAD")
        | git_paths("diff", "--name-only", "HEAD")
        | git_paths("ls-files", "--others", "--exclude-standard")
    )
    files = sorted(p for p in files if Path(p).is_file())
    for tool in ("bash", "shellcheck") + (
        ("terraform", "terragrunt") if (ROOT / "terragrunt.hcl").exists() else ()
    ):
        if not shutil.which(tool):
            raise ValueError(f"Required tool missing: {tool}; see docs/agent-workflow.md")
    secret = re.compile(
        r"(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_"
        + r"[A-Za-z0-9]{36,}|-----BEGIN "
        + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    )
    legacy_fmt = 0
    for name in files:
        path = Path(name)
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            continue
        if secret.search(content):
            raise ValueError(f"Possible credential in {name}; value withheld")
        if path.suffix == ".py":
            ast.parse(content, filename=name)
        if path.suffix == ".json":
            value = load_json(path)
            validate_config(path, value)
        if path.suffix == ".sh":
            run(["bash", "-n", name])
            if name in changed:
                run(["shellcheck", "--severity=warning", name])
        if path.suffix == ".tf":
            result = subprocess.run(
                ["terraform", "fmt", "-check", "-diff", name], capture_output=True, text=True
            )
            if result.returncode not in (0, 3) or (result.returncode and name in changed):
                print(result.stdout, result.stderr)
                raise ValueError(f"Terraform syntax/changed-file formatting failed: {name}")
            legacy_fmt += result.returncode == 3
    if (ROOT / "terragrunt.hcl").exists():
        run(["terragrunt", "hcl", "fmt", "--check", "--file", "terragrunt.hcl"])
        run(["terragrunt", "hcl", "validate"])
        print(f"Unchanged Terraform files with legacy formatting differences: {legacy_fmt}")
    python_changed = sorted(
        name for name in changed if name.endswith(".py") and Path(name).is_file()
    )
    if python_changed:
        run(["ruff", "check", *python_changed])
        run(["ruff", "format", "--check", *python_changed])
    if (ROOT / "terragrunt.hcl").exists():
        from static_security import check

        check(base)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(["git", "diff", "--check", base])
    if args.terraform:
        if not (ROOT / "components").is_dir():
            raise ValueError("--terraform is available only in aws-iac")
        provider_validate(args.terraform)
    if args.terraform_changed:
        failed = []
        for component in sorted(
            {
                Path(name).parts[1]
                for name in changed
                if name.startswith("components/") and name.endswith(".tf")
            }
        ):
            try:
                status = load_json(ROOT / "components/status.json").get(component, {})
                if status.get("status") == "incomplete":
                    # Quarantined prototypes must stay semantically unchanged until valid implementation/review.
                    import hcl2

                    for path in (ROOT / "components" / component).glob("*.tf"):
                        old = subprocess.check_output(
                            ["git", "show", f"{base}:{path.relative_to(ROOT)}"], text=True
                        )
                        if hcl2.loads(old) != hcl2.loads(path.read_text()):
                            raise ValueError(
                                "Incomplete component changed; implement and validate before promotion: "
                                + component
                            )
                    print("Verified unchanged quarantined prototype: " + component)
                    continue
                provider_validate(component)
            except subprocess.CalledProcessError:
                failed.append(component)
        if failed:
            raise ValueError("Provider validation failed for: " + ", ".join(failed))
    print("Repository verification passed. No AWS calls or Terraform state writes performed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, SyntaxError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"Verification FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
