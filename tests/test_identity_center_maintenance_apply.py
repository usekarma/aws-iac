"""Sealed same-owner maintenance apply, using synthetic files and mocked tools."""

import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
m = importlib.import_module("maintain_identity_center")
maintenance_test_helpers = importlib.import_module("test_identity_center_maintenance")


class MaintenanceApplyTests(unittest.TestCase):
    def setUp(self):
        maintenance_test_helpers.MaintenanceTests.setUp(self)
        self.env["AWS_MUTATION_APPROVED"] = "1"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.owner = self.root / "owner"
        self.owner.mkdir()
        self.out = self.owner / "maintenance-reviews/config-read-test"
        self.out.mkdir(parents=True)
        self.state = {
            "lineage": "synthetic-lineage",
            "serial": 4,
            "resources": [{"mode": "managed", "type": "synthetic-test-only"}],
        }
        (self.owner / "terraform.tfstate").write_text(json.dumps(self.state))
        (self.owner / ".terraform").mkdir()
        (self.owner / ".terraform/terraform.tfstate").write_text("synthetic-backend")
        (self.owner / ".terraform.lock.hcl").write_text("synthetic-lock")
        (self.owner / "review-manifest.json").write_text("synthetic-original-manifest")
        (self.owner / "post-apply.json").write_text("synthetic-postflight")
        (self.root / "scripts").mkdir()
        for name in ("maintain_identity_center.py", "bootstrap_identity_center.py", "evidence.py"):
            shutil.copy(ROOT / "scripts" / name, self.root / "scripts" / name)
        (self.root / "examples").mkdir()
        for name in (m.DECLARATION, m.bootstrap.DECLARATION):
            shutil.copy(ROOT / name, self.root / name)
        shutil.copytree(
            ROOT / "components" / m.bootstrap.COMPONENT,
            self.root / "components" / m.bootstrap.COMPONENT,
        )
        for source in (ROOT / "components" / m.bootstrap.COMPONENT).glob("*.tf"):
            shutil.copy(source, self.owner / source.name)
        (self.owner / "bootstrap_override.tf").write_text('terraform {\n  backend "local" {}\n}\n')
        self.inputs = {"bootstrap_config_json": json.dumps(self.old)}
        (self.owner / "bootstrap.tfvars.json").write_text(json.dumps(self.inputs))
        self.inputs = {"bootstrap_config_json": json.dumps(self.new)}
        (self.out / "maintenance.tfvars.json").write_text(json.dumps(self.inputs))
        self.plan = maintenance_test_helpers.MaintenanceTests.fixture(self)
        self.plan["variables"] = {k: {"value": v} for k, v in self.inputs.items()}
        context = {
            "synthetic": False,
            "component": m.bootstrap.COMPONENT,
            "account": m.bootstrap.OWNER,
            "region": "us-east-1",
            "profile": "identity-center-admin",
        }
        (self.out / "context.json").write_text(json.dumps(context))
        (self.out / "owner.json").write_text(
            json.dumps(
                {
                    "owner_directory": str(self.owner),
                    "lineage": self.state["lineage"],
                    "serial": 4,
                    "state_sha256": m.bootstrap.sha256(self.owner / "terraform.tfstate"),
                    "declaration_sha256": m.bootstrap.sha256(self.root / m.DECLARATION),
                }
            )
        )
        (self.out / "evidence").mkdir()
        (self.out / "evidence/summary.md").write_text("synthetic-review")
        self.rebuild()
        self.calls = []
        self.live_policies = []
        for patcher in (
            patch.object(m, "ROOT", self.root),
            patch.object(m, "validate_owner", side_effect=self.validate_owner),
            patch.object(m.bootstrap, "review_directory", return_value=self.owner),
            patch.object(
                m.bootstrap,
                "repository_identity",
                return_value={"name": "usekarma/aws-iac", "commit": "b" * 40},
            ),
            patch.object(m.bootstrap, "verify_ancestor"),
            patch.object(m, "live_checks", side_effect=self.live),
            patch.object(
                m, "workload_probe", return_value="GetParameter permitted; ParameterNotFound"
            ),
            patch.object(m.subprocess, "run", side_effect=self.terraform),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)

    def validate_owner(self, path, old):
        self.assertEqual(Path(path), self.owner)
        self.assertEqual(old, self.old)
        if any(
            (self.owner / f.name).read_bytes() != f.read_bytes()
            for f in (self.root / "components" / m.bootstrap.COMPONENT).glob("*.tf")
        ):
            raise ValueError("source changed")
        return self.owner, self.state, "synthetic-arn"

    def rebuild(self):
        with zipfile.ZipFile(self.out / "review.tfplan", "w") as archive:
            for source in self.owner.glob("*.tf"):
                archive.write(source, "tfconfig/m-/" + source.name)
            archive.write(self.owner / ".terraform.lock.hcl", ".terraform.lock.hcl")
            archive.writestr("tfstate-prev", json.dumps(self.state))
        (self.out / "plan.json").write_text(json.dumps(self.plan))
        (self.out / "evidence/evidence.json").write_text(
            json.dumps(
                {
                    "repository_commit": "a" * 40,
                    "context": json.loads((self.out / "context.json").read_text()),
                    "source": {
                        "synthetic": False,
                        "plan_json_sha256": m.bootstrap.sha256(self.out / "plan.json"),
                        "saved_plan_sha256": m.bootstrap.sha256(self.out / "review.tfplan"),
                    },
                }
            )
        )

    def terraform(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(kwargs["cwd"], self.owner)
        if command[1] == "show":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.plan))
        self.assertEqual(
            command,
            ["terraform", "apply", "-input=false", "-no-color", str(self.out / "review.tfplan")],
        )
        return subprocess.CompletedProcess(command, 0)

    def live(self, env, arn, policy):
        self.live_policies.append(policy)
        return {"Account": m.bootstrap.OWNER}

    def seal(self):
        return m.seal_review(self.env, self.owner, self.out)

    def assert_no_apply(self):
        self.assertFalse(any(c[1] == "apply" for c in self.calls))

    def test_agents_and_both_approvals_required_before_tools(self):
        for overrides in (
            {"AGENT_MODE": "1"},
            {"HUMAN_MAINTENANCE_APPROVED": ""},
            {"AWS_MUTATION_APPROVED": ""},
            {"AWS_PROFILE": "strall-dev-plan"},
        ):
            with self.assertRaises(ValueError):
                m.maintenance_apply(self.env | overrides, self.owner, self.out, "f" * 64)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.live_policies, [])

    def test_wrong_digest_and_altered_material_stop_before_mutation(self):
        digest = self.seal()
        with self.assertRaises(ValueError):
            m.maintenance_apply(self.env, self.owner, self.out, "0" * 64)
        for base, name in (
            (self.out, "review.tfplan"),
            (self.out, "plan.json"),
            (self.owner, "terraform.tfstate"),
            (self.owner, ".terraform.lock.hcl"),
            (self.owner, "main.tf"),
            (self.out, "evidence/summary.md"),
        ):
            original = (base / name).read_bytes()
            (base / name).write_bytes(original + b"changed")
            with self.assertRaises(ValueError):
                m.maintenance_apply(self.env, self.owner, self.out, digest)
            (base / name).write_bytes(original)
        with self.assertRaises(ValueError):
            self.seal()
        self.assert_no_apply()

    def test_non_update_scope_drift_and_policy_expansion_rejected(self):
        original = copy.deepcopy(self.plan)
        for actions in (["create"], ["delete"], ["delete", "create"]):
            self.plan = copy.deepcopy(original)
            self.plan["resource_changes"][2]["change"]["actions"] = actions
            self.rebuild()
            with self.assertRaises(ValueError):
                self.seal()
        self.plan = copy.deepcopy(original)
        self.plan["resource_changes"][0]["change"]["after"]["session_duration"] = "PT8H"
        self.rebuild()
        with self.assertRaises(ValueError):
            self.seal()
        self.plan = copy.deepcopy(original)
        self.plan["resource_changes"][1]["change"]["after"] = dict(
            self.plan["resource_changes"][1]["change"]["before"]
        ) | {"principal_id": "wrong"}
        self.rebuild()
        with self.assertRaises(ValueError):
            self.seal()
        for action in (True, False):
            self.plan = copy.deepcopy(original)
            policy = copy.deepcopy(self.new["inline_policy"])
            if action:
                policy["Statement"][1]["Action"] = ["ssm:GetParameter", "ssm:PutParameter"]
            else:
                policy["Statement"][1]["Resource"].append(
                    "arn:aws:ssm:us-east-1:623155450153:parameter/iac/unrelated"
                )
            self.plan["resource_changes"][2]["change"]["after"]["inline_policy"] = json.dumps(
                policy
            )
            self.rebuild()
            with self.assertRaises(ValueError):
                self.seal()
        self.assert_no_apply()

    def test_exact_saved_plan_same_owner_and_verified_postflight(self):
        before = m.bootstrap.sha256(self.owner / "terraform.tfstate")
        digest = self.seal()
        m.maintenance_apply(self.env, self.owner, self.out, digest)
        self.assertEqual([c[1] for c in self.calls], ["show", "show", "apply"])
        self.assertEqual(self.live_policies, [self.old, self.new])
        self.assertEqual(m.bootstrap.sha256(self.owner / "terraform.tfstate"), before)
        self.assertFalse((self.out / "terraform.tfstate").exists())
        self.assertEqual(
            json.loads((self.out / "post-apply.json").read_text())["status"], "verified"
        )

    def test_postflight_failure_recorded_without_reapply(self):
        digest = self.seal()

        def live(env, arn, policy):
            if policy == self.new:
                raise ValueError("unexpected managed policy")
            return {}

        with patch.object(m, "live_checks", side_effect=live):
            with self.assertRaises(ValueError):
                m.maintenance_apply(self.env, self.owner, self.out, digest)
        self.assertEqual(sum(c[1] == "apply" for c in self.calls), 1)
        self.assertEqual(
            json.loads((self.out / "post-apply.json").read_text())["status"], "postflight-failed"
        )

    def test_restricted_probe_accepts_notfound_not_denied_and_no_ssm_write(self):
        identity = {
            "Account": "623155450153",
            "Arn": "arn:aws:sts::623155450153:assumed-role/AWSReservedSSO_IaCPlanReadOnly_test/admin",
        }

        def result(stderr):
            return subprocess.CompletedProcess([], 254, stdout="", stderr=stderr)

        # Unpatch the probe while keeping every external call mocked.
        original_probe = self.__class__.real_probe
        with (
            patch.object(m.bootstrap, "aws", return_value=identity),
            patch.object(
                m.subprocess,
                "run",
                return_value=result("(ParameterNotFound) when calling the GetParameter operation"),
            ) as run,
        ):
            self.assertIn("ParameterNotFound", original_probe(self.env))
            self.assertEqual(run.call_args.args[0][2], "strall-dev-plan")
            self.assertIn("get-parameter", run.call_args.args[0])
        with (
            patch.object(m.bootstrap, "aws", return_value=identity),
            patch.object(m.subprocess, "run", return_value=result("AccessDenied")),
        ):
            with self.assertRaises(ValueError):
                original_probe(self.env)

    real_probe = staticmethod(m.workload_probe)
    real_live_checks = staticmethod(m.live_checks)

    def test_real_postflight_checks_policy_and_both_managed_policy_lists(self):
        def api(env, service, action, *args):
            values = {
                "get-caller-identity": {
                    "Account": m.bootstrap.OWNER,
                    "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_test/admin",
                },
                "describe-permission-set": {
                    "PermissionSet": {"Name": "IaCPlanReadOnly", "SessionDuration": "PT1H"}
                },
                "get-inline-policy-for-permission-set": {
                    "InlinePolicy": json.dumps(self.new["inline_policy"])
                },
                "list-managed-policies-in-permission-set": {"AttachedManagedPolicies": []},
                "list-customer-managed-policy-references-in-permission-set": {
                    "CustomerManagedPolicyReferences": []
                },
                "list-account-assignments": {
                    "AccountAssignments": [
                        {
                            "AccountId": "623155450153",
                            "PrincipalType": "USER",
                            "PrincipalId": m.bootstrap.PRINCIPAL,
                        }
                    ]
                },
            }
            return values[action]

        with patch.object(m.bootstrap, "aws", side_effect=api):
            self.__class__.real_live_checks(self.env, "synthetic", self.new)
        for operation, value in (
            (
                "list-managed-policies-in-permission-set",
                {"AttachedManagedPolicies": [{"Arn": "unexpected"}]},
            ),
            (
                "list-customer-managed-policy-references-in-permission-set",
                {"CustomerManagedPolicyReferences": [{"Name": "unexpected"}]},
            ),
            ("get-inline-policy-for-permission-set", {"InlinePolicy": "{}"}),
        ):

            def changed(env, service, action, *args):
                return value if action == operation else api(env, service, action, *args)

            with patch.object(m.bootstrap, "aws", side_effect=changed):
                with self.assertRaises(ValueError):
                    self.__class__.real_live_checks(self.env, "synthetic", self.new)
