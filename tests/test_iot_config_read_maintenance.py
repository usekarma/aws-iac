"""Human saved-plan execution using synthetic files and mocked tools only."""

import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
m = importlib.import_module("maintain_iot_config_read")
helpers = importlib.import_module("test_iot_config_read_plan")
legacy = importlib.import_module("maintain_identity_center")
evidence = importlib.import_module("evidence")


class ConfigReadMaintenanceTests(unittest.TestCase):
    def setUp(self):
        helper = helpers.ExactReadProposalTests()
        helper.setUp()
        self.old, self.new = helper.old, helper.new
        self.managed = copy.deepcopy(helper.managed)
        self.plan = copy.deepcopy(helper.fixture)
        self.plan["format_version"] = "1.2"
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.owner = self.root / "artifacts/identity-center-bootstrap/review-uhd86fs8"
        self.owner.mkdir(parents=True)
        self.out = self.owner / "maintenance-reviews" / m.REVIEW_NAME
        self.out.mkdir(parents=True)
        self.pub = self.owner / "maintenance-reviews" / m.proposal.PUB_REVIEW
        self.pub.mkdir()
        for name in (m.proposal.DECLARATION, m.PLANNER, m.EXECUTOR):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, destination)
        self.state = {"lineage": m.proposal.LINEAGE, "serial": 13, "resources": []}
        for address, attrs in self.managed.items():
            base, _, index = address.partition("[")
            kind, name = base.split(".")
            instance = {"attributes": attrs}
            if index:
                instance["index_key"] = json.loads(index[:-1])
            self.state["resources"].append(
                {"mode": "managed", "type": kind, "name": name, "instances": [instance]}
            )
        (self.owner / "terraform.tfstate").write_text(json.dumps(self.state))
        self.state_hash = m.proposal.sha(self.owner / "terraform.tfstate")
        (self.owner / ".terraform").mkdir()
        for name in (
            "main.tf",
            "header.tf",
            "outputs.tf",
            "bootstrap_override.tf",
            ".terraform.lock.hcl",
            ".terraform/terraform.tfstate",
            "review-manifest.json",
            "post-apply.json",
        ):
            (self.owner / name).write_text("synthetic original " + name)
        self.owner_names = {p.name for p in self.owner.glob("*.tf")} | {
            "terraform.tfstate",
            ".terraform.lock.hcl",
            ".terraform/terraform.tfstate",
            "review-manifest.json",
            "post-apply.json",
            "bootstrap.tfvars.json",
        }
        (self.owner / "bootstrap.tfvars.json").write_text(
            json.dumps({"bootstrap_config_json": "historical"})
        )
        (self.pub / m.proposal.OVERLAY).write_text("synthetic publisher source")
        (self.out / m.proposal.OVERLAY).write_bytes((self.pub / m.proposal.OVERLAY).read_bytes())
        for name in (
            "artifact-publisher-manifest.json",
            "apply.log",
            "apply-result.json",
            "post-apply.json",
            m.proposal.RECEIPT,
        ):
            path = self.pub / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic historical " + name)
        variables = {"bootstrap_config_json": json.dumps(self.new)}
        (self.out / "maintenance.tfvars.json").write_text(json.dumps(variables))
        self.plan["variables"] = {k: {"value": v} for k, v in variables.items()}
        (self.out / "plan.json").write_text(json.dumps(self.plan))
        with zipfile.ZipFile(self.out / "review.tfplan", "w") as archive:
            for path in self.owner.glob("*.tf"):
                archive.write(path, "tfconfig/m-/" + path.name)
            archive.write(self.out / m.proposal.OVERLAY, "tfconfig/m-/" + m.proposal.OVERLAY)
            archive.write(self.owner / ".terraform.lock.hcl", ".terraform.lock.hcl")
            archive.writestr("tfstate-prev", json.dumps(self.state))
        self.plan_hash = m.proposal.sha(self.out / "review.tfplan")
        self.json_hash = m.proposal.sha(self.out / "plan.json")
        source = (self.root / m.PLANNER).read_bytes()
        original = source.replace(b"execution.publisher.generate(", b"execution.generate(", 1)
        (self.out / "planning-script.py").write_bytes(original)
        old_script_hash = m.proposal.sha(self.out / "planning-script.py")
        new_script_hash = m.proposal.sha(self.root / m.PLANNER)
        repair = {
            "operation": "local-evidence-generation-repair-only",
            "original_planning_script_sha256": old_script_hash,
            "corrected_script_sha256": new_script_hash,
            "saved_plan_sha256": self.plan_hash,
            "plan_json_sha256": self.json_hash,
            "state_sha256": self.state_hash,
            "live_plan_regenerated": False,
            "aws_operations": [],
        }
        (self.out / "evidence-repair.json").write_text(json.dumps(repair))
        (self.out / "terraform.log").write_text("synthetic reviewed plan log")
        context = {k: "synthetic contextual label" for k in evidence.CONTEXT}
        context.update(
            component="identity-center-permission-set",
            account="835990279085",
            region="us-east-1",
            profile="identity-center-plan",
            synthetic=False,
        )
        (self.out / "context.json").write_text(json.dumps(context))
        (self.out / "evidence").mkdir()
        (self.out / "evidence/summary.md").write_text("synthetic unit review")
        (self.out / "evidence/evidence.json").write_text(
            json.dumps(
                {
                    "repository_commit": "a" * 40,
                    "context": {k: context[k] for k in evidence.CONTEXT},
                    "source": {
                        "synthetic": False,
                        "saved_plan_sha256": self.plan_hash,
                        "plan_json_sha256": self.json_hash,
                    },
                }
            )
        )
        record = {
            "owner_directory": str(self.owner),
            "lineage": m.proposal.LINEAGE,
            "serial": 13,
            "state_sha256": self.state_hash,
            "saved_plan_sha256": self.plan_hash,
            "plan_json_sha256": self.json_hash,
            "granted_resource": m.proposal.SSM_ARN,
            "creates": 0,
            "changes": 1,
            "deletes": 0,
            "owner_inputs": self.hashes(self.owner, self.owner_names),
            "proposal_inputs": {
                m.proposal.DECLARATION: m.proposal.sha(self.root / m.proposal.DECLARATION),
                m.PLANNER: old_script_hash,
            },
            "previous_verified_review": str(self.pub / m.proposal.RECEIPT),
            "previous_review_sha256": m.proposal.sha(self.pub / m.proposal.RECEIPT),
            "identity": {
                "Account": "835990279085",
                "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_abcdef/human",
            },
        }
        (self.out / "owner.json").write_text(json.dumps(record))
        self.baseline = {
            "instance": {"InstanceArn": m.proposal.INSTANCE},
            "permission_sets": {
                m.proposal.PS_ARN: {
                    "inline_policy": self.old["inline_policy"],
                    "assignments": [
                        "623155450153/USER/" + m.proposal.PRINCIPAL,
                        "835990279085/USER/" + m.proposal.PRINCIPAL,
                    ],
                    "managed_policies": [],
                },
                m.proposal.PUB_ARN: {
                    "inline_policy": {"Statement": ["synthetic preserved publisher"]},
                    "assignments": ["623155450153/USER/" + m.proposal.PRINCIPAL],
                    "managed_policies": [],
                },
                "synthetic-unrelated": {"name": "unchanged", "managed_policies": []},
            },
        }
        self.calls = []
        self.inventory_calls = 0
        self.post = False
        self.returncode = 0
        self.drift = None
        self.after_drift = None
        self.probe_result = subprocess.CompletedProcess(
            [],
            254,
            stdout="",
            stderr="An error occurred (ParameterNotFound) when calling the GetParameter operation",
        )
        self.env = {
            "AGENT_MODE": "0",
            "HUMAN_MAINTENANCE_APPROVED": "1",
            "AWS_MUTATION_APPROVED": "1",
            "AWS_PROFILE": "identity-center-admin",
            "AWS_REGION": "us-east-1",
            "EXPECTED_AWS_ACCOUNT": "835990279085",
        }
        self.execution = SimpleNamespace(
            guard=self.human_guard,
            CONTEXT=evidence.CONTEXT,
            safe_hashes=self.hashes,
            owner_files=lambda owner: self.owner_names,
            owner_workflow=SimpleNamespace(
                owner_directory=self.owner_directory, managed_state=self.state_map, write=self.write
            ),
            bootstrap=SimpleNamespace(
                verify_ancestor=lambda _: None, git=lambda *args: "a" * 40, aws=self.read_aws
            ),
            maintenance=SimpleNamespace(read_saved_plan=self.show),
            publisher=SimpleNamespace(declaration=lambda: {"synthetic": "publisher unchanged"}),
            inventory=self.inventory,
            require_entry=lambda *args: None,
            attempted=lambda out: any(
                (out / n).exists() for n in ("apply.log", "apply-result.json", "post-apply.json")
            ),
            verify_manifest=lambda *args, **kwargs: None,
            PLANNING_INPUTS=set(),
            EXECUTOR="scripts/mock-historical-executor.py",
        )
        (self.root / self.execution.EXECUTOR).write_text("synthetic sealed helper")
        (self.root / "scripts/recheck_artifact_publisher.py").write_text(
            "synthetic recovery helper"
        )
        for patcher in (
            patch.object(m, "ROOT", self.root),
            patch.object(m.proposal, "ROOT", self.root),
            patch.object(m.proposal, "OWNER", self.owner),
            patch.object(m.proposal, "OWNER_REPO", self.root),
            patch.object(m.proposal, "STATE_SHA256", self.state_hash),
            patch.object(
                m.proposal, "RECEIPT_SHA256", m.proposal.sha(self.pub / m.proposal.RECEIPT)
            ),
            patch.object(m, "PLAN_SHA256", self.plan_hash),
            patch.object(m, "PLAN_JSON_SHA256", self.json_hash),
            patch.object(m, "ORIGINAL_SCRIPT_SHA256", old_script_hash),
            patch.object(m, "CORRECTED_SCRIPT_SHA256", new_script_hash),
            patch.object(m.proposal, "runtime", return_value=(self.execution, None)),
            patch.object(m.proposal, "validate_owner", side_effect=self.validate_owner),
            patch.object(m.subprocess, "run", side_effect=self.tool_run),
            patch("builtins.print"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        mode = os.umask(0o077)
        self.addCleanup(os.umask, mode)

    def hashes(self, base, names):
        return {n: m.proposal.sha(base / n) for n in sorted(names)}

    def write(self, path, value):
        with path.open("x") as f:
            f.write(json.dumps(value, indent=2) + "\n")

    def human_guard(self, env, mutation=False):
        legacy.guard(env)
        if mutation and env.get("AWS_MUTATION_APPROVED") != "1":
            raise ValueError("mutation approval required")
        return env

    def owner_directory(self, path):
        if Path(path) != self.owner:
            raise ValueError("no second owner")
        return self.owner

    def state_map(self, state):
        result = {}
        for resource in state["resources"]:
            for instance in resource["instances"]:
                address = resource["type"] + "." + resource["name"]
                if "index_key" in instance:
                    address += "[" + json.dumps(instance["index_key"]) + "]"
                result[address] = instance["attributes"]
        return result

    def validate_owner(self, env, execution, recovery):
        state = json.loads((self.owner / "terraform.tfstate").read_text())
        if m.proposal.sha(self.owner / "terraform.tfstate") != self.state_hash:
            raise ValueError("baseline state changed")
        return state, self.state_map(state), self.pub

    def show(self, owner, out, env):
        self.assertEqual(owner, self.owner)
        self.calls.append(["terraform", "show", "-json", str(out / "review.tfplan")])
        return self.plan

    def read_aws(self, env, *args):
        self.assertEqual(env["AWS_PROFILE"], "strall-dev-plan")
        self.assertEqual(args, ("sts", "get-caller-identity"))
        return {
            "Account": "623155450153",
            "Arn": "arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_IaCPlanReadOnly_abcdef/human",
        }

    def inventory(self, env):
        self.inventory_calls += 1
        snapshot = copy.deepcopy(self.baseline)
        if self.post:
            snapshot["permission_sets"][m.proposal.PS_ARN]["inline_policy"] = self.new[
                "inline_policy"
            ]
        if self.drift == "assignment":
            snapshot["permission_sets"][m.proposal.PS_ARN]["assignments"].pop()
        if self.drift == "managed":
            snapshot["permission_sets"][m.proposal.PS_ARN]["managed_policies"].append("unexpected")
        if self.drift == "other":
            snapshot["permission_sets"]["synthetic-unrelated"]["name"] = "changed"
        if self.drift == "policy":
            snapshot["permission_sets"][m.proposal.PS_ARN]["inline_policy"] = {"Statement": []}
        return {"Account": "835990279085"}, snapshot

    def tool_run(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == "aws":
            self.assertEqual(
                command[command.index("--name") + 1], "/iac/iot-digital-twin/core2-aws-001/config"
            )
            self.assertIn("get-parameter", command)
            self.assertNotIn("put-parameter", command)
            return self.probe_result
        self.assertEqual(
            command,
            ["terraform", "apply", "-input=false", "-no-color", str(self.out / "review.tfplan")],
        )
        self.assertEqual(kwargs["cwd"], self.owner)
        if self.returncode == 0:
            self.state["serial"] += 1
            for resource in self.state["resources"]:
                if resource["type"] + "." + resource["name"] == m.proposal.POLICY:
                    resource["instances"][0]["attributes"]["inline_policy"] = json.dumps(
                        self.new["inline_policy"]
                    )
            (self.owner / "terraform.tfstate").write_text(json.dumps(self.state))
            self.post = True
            self.drift = self.after_drift
        return subprocess.CompletedProcess(command, self.returncode)

    def seal(self):
        return m.seal(self.env, self.owner, self.out)

    def assert_no_apply(self):
        self.assertFalse(any(c[:2] == ["terraform", "apply"] for c in self.calls))

    def test_agents_and_both_human_acknowledgements_required_before_tools(self):
        for func, args in (
            (m.seal, (self.owner, self.out)),
            (m.apply, (self.owner, self.out, "0" * 64)),
            (m.postflight, (self.owner, self.out, "0" * 64)),
        ):
            for overrides in (
                {"AGENT_MODE": "1"},
                {"AGENT_MODE": ""},
                {"HUMAN_MAINTENANCE_APPROVED": ""},
                {"AWS_PROFILE": "identity-center-plan"},
                {"EXPECTED_AWS_ACCOUNT": "623155450153"},
                {"AWS_REGION": "us-west-2"},
            ):
                with (
                    self.subTest(function=func.__name__, overrides=overrides),
                    self.assertRaises(ValueError),
                ):
                    func(self.env | overrides, *args)
        with self.assertRaises(ValueError):
            m.apply(self.env | {"AWS_MUTATION_APPROVED": ""}, self.owner, self.out, "0" * 64)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.inventory_calls, 0)

    def test_seal_preserves_exact_plan_and_review_inputs(self):
        original = {p: p.read_bytes() for p in self.owner.rglob("*") if p.is_file()}
        digest = self.seal()
        for path, contents in original.items():
            self.assertEqual(path.read_bytes(), contents)
        self.assertEqual(digest, m.proposal.sha(self.out / m.MANIFEST))
        with self.assertRaises(ValueError):
            self.seal()
        self.assert_no_apply()

    def test_wrong_digest_and_sealed_source_state_backend_lock_plan_drift_block(self):
        digest = self.seal()
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, "0" * 64)
        for base, name in (
            (self.owner, "terraform.tfstate"),
            (self.owner, "main.tf"),
            (self.owner, ".terraform.lock.hcl"),
            (self.owner, ".terraform/terraform.tfstate"),
            (self.root, m.PLANNER),
            (self.root, m.EXECUTOR),
            (self.root, m.proposal.DECLARATION),
            (self.out, "review.tfplan"),
            (self.out, "plan.json"),
            (self.out, "evidence-repair.json"),
        ):
            path = base / name
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.apply(self.env, self.owner, self.out, digest)
            path.write_bytes(original)
        self.assert_no_apply()

    def test_explicit_repair_accepts_only_generator_reference_change(self):
        m.validate_bundle(self.env, self.owner, self.out, self.execution, None)
        path = self.out / "planning-script.py"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        with self.assertRaises(ValueError):
            self.seal()
        path.write_bytes(original)
        repair = json.loads((self.out / "evidence-repair.json").read_text())
        repair["live_plan_regenerated"] = True
        (self.out / "evidence-repair.json").write_text(json.dumps(repair))
        with self.assertRaises(ValueError):
            self.seal()
        self.assert_no_apply()

    def test_exact_saved_apply_and_parameter_notfound_authorization_postflight(self):
        digest = self.seal()
        self.calls.clear()
        result = m.apply(self.env, self.owner, self.out, digest)
        self.assertEqual([c[1] for c in self.calls], ["show", "apply", "show", "--profile"])
        self.assertTrue(result["planner_config_probe"]["authorized"])
        self.assertFalse(result["planner_config_probe"]["parameter_exists"])
        self.assertEqual(result["verification_scope"], "IAM config-read maintenance only")
        self.assertFalse(result["config_publication_performed"])
        self.assertEqual(result["ingestion_readiness"], "NOT_VERIFIED")
        self.assertEqual(result["action_count"], 32)
        self.assertTrue(result["assignments_unchanged"])
        self.assertFalse((self.out / "terraform.tfstate").exists())
        self.assertFalse((self.owner / m.proposal.OVERLAY).exists())
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, digest)
        m.postflight(self.env, self.owner, self.out, digest)
        self.assertEqual(sum(c[:2] == ["terraform", "apply"] for c in self.calls), 1)

    def test_config_probe_existing_parameter_and_access_denied_fail_closed(self):
        self.probe_result = subprocess.CompletedProcess([], 0, stdout="4")
        self.assertEqual(m.planner_probe(self.env, self.execution)["version"], 4)
        self.probe_result = subprocess.CompletedProcess(
            [],
            254,
            stdout="",
            stderr="AccessDeniedException ssm:GetParameter " + m.proposal.SSM_ARN,
        )
        with self.assertRaisesRegex(ValueError, "AccessDenied"):
            m.planner_probe(self.env, self.execution)
        self.assert_no_apply()

    def test_failed_apply_does_not_retry_rollback_or_claim_postflight(self):
        digest = self.seal()
        self.returncode = 1
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, digest)
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, digest)
        with self.assertRaises(ValueError):
            m.postflight(self.env, self.owner, self.out, digest)
        self.assertEqual(sum(c[:2] == ["terraform", "apply"] for c in self.calls), 1)

    def test_postflight_detects_policy_assignment_managed_and_unrelated_drift(self):
        digest = self.seal()
        m.apply(self.env, self.owner, self.out, digest)
        for drift in ("policy", "assignment", "managed", "other"):
            self.drift = drift
            with self.subTest(drift=drift), self.assertRaises(ValueError):
                m.postflight(self.env, self.owner, self.out, digest)
        self.assertEqual(sum(c[:2] == ["terraform", "apply"] for c in self.calls), 1)

    def test_postflight_failure_is_recorded_and_only_readonly_recheck_can_repeat(self):
        digest = self.seal()
        self.after_drift = "policy"
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, digest)
        self.assertFalse(json.loads((self.out / "post-apply.json").read_text())["automatic_retry"])
        with self.assertRaises(ValueError):
            m.apply(self.env, self.owner, self.out, digest)
        failure = (self.out / "post-apply.json").read_bytes()
        self.drift = None
        m.postflight(self.env, self.owner, self.out, digest)
        self.assertEqual((self.out / "post-apply.json").read_bytes(), failure)
        receipts = list((self.out / "postflight-rechecks").glob("review-*/postflight.json"))
        self.assertEqual(len(receipts), 1)
        recheck = json.loads(receipts[0].read_text())
        self.assertEqual(recheck["status"], "verified")
        self.assertEqual(
            recheck["previous_postflight_sha256"], m.proposal.sha(self.out / "post-apply.json")
        )

    def test_state_owner_and_other_managed_attributes_remain_strict(self):
        digest = self.seal()
        m.apply(self.env, self.owner, self.out, digest)
        current = copy.deepcopy(self.state)
        for change in (
            lambda s: s.update(lineage="other"),
            lambda s: s["resources"].pop(),
            lambda s: s["resources"][0]["instances"][0]["attributes"].update(id="changed"),
        ):
            changed = copy.deepcopy(current)
            change(changed)
            (self.owner / "terraform.tfstate").write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                m.postflight(self.env, self.owner, self.out, digest)

    def test_changed_json_binary_and_unexpected_plan_actions_stop_seal(self):
        original = copy.deepcopy(self.plan)
        for address in [row["address"] for row in original["resource_changes"]]:
            for actions in (["create"], ["delete"], ["delete", "create"]):
                self.plan = copy.deepcopy(original)
                row = next(
                    row for row in self.plan["resource_changes"] if row["address"] == address
                )
                row["change"]["actions"] = actions
                with self.assertRaises(ValueError):
                    self.seal()
        self.plan = original
        self.assert_no_apply()

    def test_cli_has_no_plan_and_requires_independent_digest(self):
        for args in (
            ["plan", "identity-center-permission-set"],
            [
                "apply",
                "identity-center-permission-set",
                "--owner-dir",
                str(self.owner),
                "--review-dir",
                str(self.out),
            ],
            ["apply", "s3-bucket"],
        ):
            with (
                patch.object(sys, "argv", ["maintenance"] + args),
                patch("sys.stderr"),
                self.assertRaises(SystemExit),
            ):
                m.main()
        self.assertEqual(self.calls, [])

    def test_seal_needs_no_mutation_flag_and_never_authorizes_apply(self):
        env = self.env | {"AWS_MUTATION_APPROVED": ""}
        digest = m.seal(env, self.owner, self.out)
        with self.assertRaises(ValueError):
            m.apply(env, self.owner, self.out, digest)
        self.assert_no_apply()
        for key in ("AGENT_MODE", "HUMAN_MAINTENANCE_APPROVED"):
            missing = dict(self.env)
            del missing[key]
            with self.assertRaises(ValueError):
                m.postflight(missing, self.owner, self.out, digest)

    def test_probe_unexpected_errors_and_mixed_notfound_diagnostics_never_confirm_permission(self):
        notfound = "An error occurred (ParameterNotFound) when calling the GetParameter operation"
        for result in (
            subprocess.CompletedProcess([], 255, stdout="", stderr=notfound),
            subprocess.CompletedProcess([], 253, stdout="", stderr="Expired SSO token"),
            subprocess.CompletedProcess(
                [], 254, stdout="", stderr=notfound + "\nEndpointConnectionError"
            ),
            subprocess.CompletedProcess([], 254, stdout="", stderr=notfound + ": AccessDenied"),
            subprocess.CompletedProcess([], 254, stdout="4", stderr=notfound),
            subprocess.CompletedProcess([], 0, stdout="null", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="true", stderr=""),
        ):
            self.probe_result = result
            with (
                self.subTest(code=result.returncode, message=result.stderr),
                self.assertRaises(ValueError),
            ):
                m.planner_probe(self.env, self.execution)
        self.probe_result = subprocess.CompletedProcess(
            [],
            254,
            stdout="",
            stderr=notfound + " (reached max retries: 0): Parameter not found.\n",
        )
        probe = m.planner_probe(self.env, self.execution)
        self.assertTrue(probe["authorized"])
        self.assertFalse(probe["parameter_exists"])

    def test_probe_wrong_actual_aws_account_or_role_blocks_before_ssm(self):
        for identity in (
            {
                "Account": "835990279085",
                "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_abcdef/user",
            },
            {
                "Account": "623155450153",
                "Arn": "arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_AdministratorAccess_abcdef/user",
            },
        ):
            with (
                patch.object(self.execution.bootstrap, "aws", return_value=identity),
                self.assertRaises(ValueError),
            ):
                m.planner_probe(self.env, self.execution)
        self.assertEqual(self.calls, [])

    def test_data_source_import_move_replacement_and_unknown_actions_are_rejected(self):
        data = {
            "address": "data.aws_caller_identity.current",
            "mode": "data",
            "type": "aws_caller_identity",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["read"], "before": None, "after": {}},
        }
        valid = copy.deepcopy(self.plan)
        valid["resource_changes"].append(data)
        m.validate_plan(valid, self.managed, self.old, self.new)
        for mutate in (
            lambda r: r.update(previous_address="data.aws_caller_identity.old"),
            lambda r: r["change"].update(importing={"id": "adopt"}),
            lambda r: r["change"].update(replace_paths=[["id"]]),
            lambda r: r["change"].update(actions=["unknown"]),
            lambda r: r.update(provider_name="registry.terraform.io/other/aws"),
        ):
            changed = copy.deepcopy(valid)
            mutate(changed["resource_changes"][-1])
            with self.assertRaises(ValueError):
                m.validate_plan(changed, self.managed, self.old, self.new)

    def test_iam_semantic_expansion_removed_condition_and_assignment_changes_fail(self):
        for mutate in (
            lambda c: c["inline_policy"]["Statement"][1].update(
                Action=["ssm:GetParameter", "ssm:PutParameter"]
            ),
            lambda c: c["inline_policy"]["Statement"][1].update(Resource="*"),
            lambda c: c["inline_policy"]["Statement"][1]["Resource"].append(
                m.proposal.SSM_ARN + "/extra"
            ),
            lambda c: c["inline_policy"]["Statement"][-1].pop("Condition"),
            lambda c: c["assignments"][0].update(principal_id="other"),
        ):
            changed = copy.deepcopy(self.new)
            mutate(changed)
            with (
                patch.object(m.proposal, "load", return_value=changed),
                self.assertRaises(ValueError),
            ):
                m.proposal.declarations()
        self.assert_no_apply()

    def test_wrong_saved_plan_hash_is_rejected_before_seal_inventory(self):
        path = self.out / "review.tfplan"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            self.seal()
        self.assertEqual(self.inventory_calls, 0)
        self.assertFalse((self.out / m.MANIFEST).exists())


if __name__ == "__main__":
    unittest.main()
