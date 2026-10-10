"""Single-ARN policy delta and same-state human maintenance safety."""

import copy
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import shutil
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
m = importlib.import_module("maintain_identity_center")


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = m.declarations()
        self.env = {
            "AGENT_MODE": "0",
            "HUMAN_MAINTENANCE_APPROVED": "1",
            "AWS_PROFILE": "identity-center-admin",
            "AWS_REGION": "us-east-1",
            "EXPECTED_AWS_ACCOUNT": m.bootstrap.OWNER,
        }

    def fixture(self):
        original = {
            "inline_policy": json.dumps(self.old["inline_policy"]),
            "instance_arn": m.bootstrap.INSTANCE,
            "permission_set_arn": "synthetic-permission-set",
        }
        changed = original | {"inline_policy": json.dumps(self.new["inline_policy"])}
        return {
            "format_version": "1.2",
            "complete": True,
            "errored": False,
            "resource_changes": [
                {
                    "address": "aws_ssoadmin_permission_set.permission_set",
                    "type": "aws_ssoadmin_permission_set",
                    "change": {
                        "actions": ["no-op"],
                        "before": {"name": "IaCPlanReadOnly", "session_duration": "PT1H"},
                        "after": {"name": "IaCPlanReadOnly", "session_duration": "PT1H"},
                    },
                },
                {
                    "address": m.bootstrap.ASSIGNMENT,
                    "type": "aws_ssoadmin_account_assignment",
                    "change": {
                        "actions": ["no-op"],
                        "before": self.old["assignments"][0],
                        "after": self.old["assignments"][0],
                    },
                },
                {
                    "address": m.POLICY_ADDRESS,
                    "type": "aws_ssoadmin_permission_set_inline_policy",
                    "change": {
                        "actions": ["update"],
                        "before": original,
                        "after": changed,
                        "after_unknown": {},
                    },
                },
            ],
        }

    def test_only_single_resource_added_and_action_set_unchanged(self):
        def actions(config):
            return {
                a
                for s in config["inline_policy"]["Statement"]
                for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
            }

        self.assertEqual(actions(self.old), actions(self.new))
        self.assertEqual(len(actions(self.new)), 24)

        def resources(config):
            return {
                a
                for s in config["inline_policy"]["Statement"]
                for a in ([s["Resource"]] if isinstance(s["Resource"], str) else s["Resource"])
            }

        self.assertEqual(resources(self.new) - resources(self.old), {m.CONFIG_ARN})
        self.assertEqual(resources(self.old) - resources(self.new), set())
        self.assertEqual(self.old["assignments"], self.new["assignments"])
        delta = copy.deepcopy(self.new)
        next(s for s in delta["inline_policy"]["Statement"] if s["Sid"] == "ReadBindingAndRuntime")[
            "Resource"
        ].remove(m.CONFIG_ARN)
        self.assertEqual(delta, self.old)

    def test_agents_and_unacknowledged_maintenance_blocked_before_tools(self):
        for overrides in (
            {"AGENT_MODE": "1", "AWS_MUTATION_APPROVED": "1"},
            {"HUMAN_MAINTENANCE_APPROVED": ""},
            {"EXPECTED_AWS_ACCOUNT": "623155450153"},
        ):
            with patch.object(m, "validate_owner") as owner:
                with self.assertRaises(ValueError):
                    m.maintenance_plan(self.env | overrides, "unused")
                owner.assert_not_called()

    def test_no_maintenance_apply_command(self):
        with patch.object(
            sys, "argv", ["maintenance", "apply", m.bootstrap.COMPONENT, "--owner-dir", "unused"]
        ):
            with self.assertRaises(SystemExit):
                m.main()

    def test_only_known_policy_update_and_no_bootstrap_replay(self):
        plan = self.fixture()
        m.validate_update(plan, self.old, self.new)
        with self.assertRaises(ValueError):
            m.bootstrap.validate_plan(plan, self.old)
        for action in (["create"], ["delete"], ["delete", "create"]):
            p = copy.deepcopy(plan)
            p["resource_changes"][2]["change"]["actions"] = action
            with self.assertRaises(ValueError):
                m.validate_update(p, self.old, self.new)
        p = copy.deepcopy(plan)
        p["resource_changes"][0]["change"]["actions"] = ["update"]
        with self.assertRaises(ValueError):
            m.validate_update(p, self.old, self.new)
        p = copy.deepcopy(plan)
        p["resource_changes"][2]["change"]["after"]["inline_policy"] = "{}"
        with self.assertRaises(ValueError):
            m.validate_update(p, self.old, self.new)
        p = copy.deepcopy(plan)
        p["resource_changes"].append(copy.deepcopy(p["resource_changes"][0]))
        with self.assertRaises(ValueError):
            m.validate_update(p, self.old, self.new)

    def test_original_owner_backend_and_state_must_be_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.object(m.bootstrap, "review_directory", return_value=work):
                with self.assertRaises(ValueError):
                    m.validate_owner(work, self.old)
            source = Path(m.__file__).read_text()
            self.assertNotIn('"init"', source)
            self.assertNotIn('"import"', source)
            self.assertNotIn('"apply"', source)
            self.assertIn("cwd=work", source)

    def test_live_mismatch_and_managed_attachments_stop_before_plan(self):
        def wrong(env, service, action, *args):
            return {"Account": "623155450153", "Arn": "wrong"}

        with patch.object(m.bootstrap, "aws", side_effect=wrong):
            with self.assertRaises(ValueError):
                m.live_checks(self.env, "synthetic", self.old)

    def test_only_valid_original_owner_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for f in (ROOT / "components" / m.bootstrap.COMPONENT).glob("*.tf"):
                shutil.copy2(f, work / f.name)
            (work / ".terraform").mkdir()
            (work / "bootstrap_override.tf").write_text('terraform {\n  backend "local" {}\n}\n')
            (work / "bootstrap.tfvars.json").write_text(
                json.dumps({"bootstrap_config_json": json.dumps(self.old)})
            )
            (work / ".terraform.lock.hcl").write_text("synthetic-lock")
            (work / ".terraform/terraform.tfstate").write_text(
                json.dumps(
                    {"backend": {"type": "local", "config": {"path": None, "workspace_dir": None}}}
                )
            )
            (work / "post-apply.json").write_text(
                json.dumps({"status": "verified", "permission_set_arn": "synthetic"})
            )
            ps = {
                "name": "IaCPlanReadOnly",
                "arn": "synthetic",
                "session_duration": "PT1H",
                "instance_arn": m.bootstrap.INSTANCE,
            }
            policy = {
                "inline_policy": json.dumps(self.old["inline_policy"]),
                "permission_set_arn": "synthetic",
                "instance_arn": m.bootstrap.INSTANCE,
            }
            assignment = {
                "target_id": "623155450153",
                "target_type": "AWS_ACCOUNT",
                "principal_type": "USER",
                "principal_id": m.bootstrap.PRINCIPAL,
                "permission_set_arn": "synthetic",
                "instance_arn": m.bootstrap.INSTANCE,
            }
            resources = [
                {
                    "mode": "managed",
                    "type": "aws_ssoadmin_permission_set",
                    "name": "permission_set",
                    "instances": [{"attributes": ps}],
                },
                {
                    "mode": "managed",
                    "type": "aws_ssoadmin_permission_set_inline_policy",
                    "name": "inline_policy",
                    "instances": [{"attributes": policy}],
                },
                {
                    "mode": "managed",
                    "type": "aws_ssoadmin_account_assignment",
                    "name": "assignment",
                    "instances": [
                        {
                            "index_key": "623155450153/USER/" + m.bootstrap.PRINCIPAL,
                            "attributes": assignment,
                        }
                    ],
                },
            ]
            (work / "terraform.tfstate").write_text(
                json.dumps({"lineage": "synthetic", "serial": 4, "resources": resources})
            )
            names = [f.name for f in work.glob("*.tf")] + [
                "bootstrap.tfvars.json",
                ".terraform.lock.hcl",
                ".terraform/terraform.tfstate",
            ]
            manifest = {
                "component": m.bootstrap.COMPONENT,
                "account": m.bootstrap.OWNER,
                "review_directory": str(work),
                "repository": {"commit": "a" * 40},
                "files": {name: m.bootstrap.sha256(work / name) for name in names},
            }
            (work / "review-manifest.json").write_text(json.dumps(manifest))
            digest = m.bootstrap.sha256(work / "review-manifest.json")
            with (
                patch.object(m.bootstrap, "review_directory", return_value=work),
                patch.object(m.bootstrap, "verify_ancestor"),
                patch.object(m, "OWNER_MANIFEST_SHA256", digest),
            ):
                owner, state, arn = m.validate_owner(work, self.old)
                self.assertEqual(owner, work)
                self.assertEqual(arn, "synthetic")
                self.assertEqual(state["lineage"], "synthetic")
                manifest["review_directory"] = str(work / "copied")
                (work / "review-manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    m.validate_owner(work, self.old)

    def test_same_state_plan_and_private_synthetic_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "terraform.tfstate").write_text(
                json.dumps({"lineage": "synthetic-lineage", "serial": 4})
            )
            (work / "bootstrap.tfvars.json").write_text(
                json.dumps({"bootstrap_config_json": json.dumps(self.old)})
            )
            calls = []
            before = m.bootstrap.sha256(work / "terraform.tfstate")

            def terraform(command, **kwargs):
                calls.append(command)
                self.assertEqual(kwargs["cwd"], work)
                if command[1] == "plan":
                    path = Path(next(arg[5:] for arg in command if arg.startswith("-out=")))
                    path.write_bytes(b"synthetic-maintenance-plan")
                elif command[1] == "show":
                    kwargs["stdout"].write(json.dumps(self.fixture()))
                else:
                    self.fail("Unexpected tool action")
                return subprocess.CompletedProcess(command, 0)

            prior = os.umask(0o077)
            try:
                with (
                    patch.object(
                        m,
                        "validate_owner",
                        return_value=(
                            work,
                            {"lineage": "synthetic-lineage", "serial": 4},
                            "synthetic",
                        ),
                    ),
                    patch.object(m, "live_checks", return_value={"Account": m.bootstrap.OWNER}),
                    patch.object(m.subprocess, "run", side_effect=terraform),
                    patch("evidence.subprocess.check_output", return_value="a" * 40),
                ):
                    out = m.maintenance_plan(self.env, work)
            finally:
                os.umask(prior)
            self.assertEqual([c[1] for c in calls], ["plan", "show"])
            self.assertEqual(before, m.bootstrap.sha256(work / "terraform.tfstate"))
            self.assertFalse((out / "terraform.tfstate").exists())
            self.assertFalse(list(out.glob("*.tf")))
            self.assertTrue((out / "evidence/evidence.json").exists())
            self.assertEqual(load_json(out / "owner.json")["lineage"], "synthetic-lineage")


def load_json(path):
    return json.loads(path.read_text())
