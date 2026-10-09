"""Human bootstrap boundaries and private plan preparation with mocked tools."""

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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
bootstrap = importlib.import_module("bootstrap_identity_center")


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "AGENT_MODE": "0",
            "HUMAN_BOOTSTRAP_APPROVED": "1",
            "AWS_PROFILE": "identity-center-admin",
            "AWS_REGION": "us-east-1",
            "EXPECTED_AWS_ACCOUNT": bootstrap.OWNER,
        }
        self.config = json.loads((ROOT / bootstrap.DECLARATION).read_text())
        self.identity = {
            "Account": bootstrap.OWNER,
            "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_44494c40ddbff199/admin",
        }
        self.discovery_calls = []

    def fake_aws(self, env, service, action, *args):
        self.discovery_calls.append((service, action))
        if action == "get-caller-identity":
            return self.identity
        if action == "list-instances":
            return {
                "Instances": [
                    {"InstanceArn": bootstrap.INSTANCE, "OwnerAccountId": bootstrap.OWNER}
                ]
            }
        if action == "list-permission-sets":
            return {"PermissionSets": ["existing"]}
        if action == "describe-permission-set":
            return {"PermissionSet": {"Name": "AdministratorAccess"}}
        self.fail("Unexpected AWS operation: " + action)

    def fixture_plan(self):
        return {
            "format_version": "1.2",
            "complete": True,
            "errored": False,
            "resource_changes": [
                {
                    "address": "aws_ssoadmin_permission_set.permission_set",
                    "type": "aws_ssoadmin_permission_set",
                    "change": {
                        "actions": ["create"],
                        "after": {
                            "name": "IaCPlanReadOnly",
                            "session_duration": "PT1H",
                            "instance_arn": bootstrap.INSTANCE,
                        },
                    },
                },
                {
                    "address": "aws_ssoadmin_permission_set_inline_policy.inline_policy",
                    "type": "aws_ssoadmin_permission_set_inline_policy",
                    "change": {
                        "actions": ["create"],
                        "after": {
                            "inline_policy": json.dumps(self.config["inline_policy"]),
                            "instance_arn": bootstrap.INSTANCE,
                        },
                    },
                },
                {
                    "address": bootstrap.ASSIGNMENT,
                    "type": "aws_ssoadmin_account_assignment",
                    "change": {
                        "actions": ["create"],
                        "after": {
                            "target_id": "623155450153",
                            "target_type": "AWS_ACCOUNT",
                            "principal_type": "USER",
                            "principal_id": bootstrap.PRINCIPAL,
                            "instance_arn": bootstrap.INSTANCE,
                        },
                    },
                },
            ],
        }

    def test_agent_and_missing_human_ack_rejected_before_aws(self):
        for overrides in ({"AGENT_MODE": "1"}, {"HUMAN_BOOTSTRAP_APPROVED": ""}):
            with patch.object(bootstrap, "aws") as aws:
                with self.assertRaises(ValueError):
                    bootstrap.plan_bootstrap(self.env | overrides)
                aws.assert_not_called()

    def test_wrong_expected_account_and_argument_overrides_rejected(self):
        for overrides in (
            {"EXPECTED_AWS_ACCOUNT": "623155450153"},
            {"TF_CLI_ARGS_plan": "-destroy"},
            {"AWS_ACCESS_KEY_ID": "synthetic"},
            {"TF_VAR_bootstrap_config_json": "{}"},
        ):
            with self.assertRaises(ValueError):
                bootstrap.guard(self.env | overrides)

    def test_wrong_actual_account_rejected_before_instance_reads(self):
        self.identity["Account"] = "623155450153"
        with patch.object(bootstrap, "aws", side_effect=self.fake_aws):
            with self.assertRaisesRegex(ValueError, "Wrong bootstrap account"):
                bootstrap.discover(self.env)
        self.assertEqual(self.discovery_calls, [("sts", "get-caller-identity")])

    def test_existing_planning_permission_set_and_missing_admin_rejected(self):
        for name in ("IaCPlanReadOnly", "Other"):

            def discovery(env, service, action, *args):
                if action == "describe-permission-set":
                    return {"PermissionSet": {"Name": name}}
                return self.fake_aws(env, service, action, *args)

            with patch.object(bootstrap, "aws", side_effect=discovery):
                with self.assertRaises(ValueError):
                    bootstrap.discover(self.env)

    def test_other_components_and_apply_are_not_callable(self):
        for args in (
            ["plan", "s3-bucket"],
            ["apply", bootstrap.COMPONENT],
            ["plan", bootstrap.COMPONENT, "--auto-approve"],
        ):
            with (
                patch.object(sys, "argv", ["bootstrap", *args]),
                patch.object(bootstrap, "plan_bootstrap") as planner,
            ):
                with self.assertRaises(SystemExit):
                    bootstrap.main()
                planner.assert_not_called()

    def test_exact_declaration_and_no_policy_expansion(self):
        bootstrap.validate_declaration(self.config)
        for key, value in (
            ("administration_account_id", "623155450153"),
            (
                "assignments",
                [
                    {
                        "target_account_id": "623155450153",
                        "principal_type": "GROUP",
                        "principal_id": bootstrap.PRINCIPAL,
                    }
                ],
            ),
            (
                "inline_policy",
                {
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}],
                },
            ),
        ):
            with self.assertRaises(ValueError):
                bootstrap.validate_declaration(self.config | {key: value})

    def test_plan_rejects_changes_deletes_unexpected_resources_and_policy(self):
        bootstrap.validate_plan(self.fixture_plan(), self.config)
        for actions in (["delete"], ["update"], ["delete", "create"]):
            plan = self.fixture_plan()
            plan["resource_changes"][0]["change"]["actions"] = actions
            with self.assertRaises(ValueError):
                bootstrap.validate_plan(plan, self.config)
        plan = self.fixture_plan()
        plan["resource_changes"].append(copy.deepcopy(plan["resource_changes"][0]))
        with self.assertRaises(ValueError):
            bootstrap.validate_plan(plan, self.config)
        plan = self.fixture_plan()
        plan["resource_changes"][1]["change"]["after"]["inline_policy"] = "{}"
        with self.assertRaises(ValueError):
            bootstrap.validate_plan(plan, self.config)
        plan = self.fixture_plan()
        plan["resource_changes"][2]["change"]["after"]["principal_id"] = "unreviewed"
        with self.assertRaises(ValueError):
            bootstrap.validate_plan(plan, self.config)

    def test_plan_is_local_private_has_no_ssm_or_apply_and_generates_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "examples").mkdir()
            shutil.copy(ROOT / bootstrap.DECLARATION, root / bootstrap.DECLARATION)
            shutil.copytree(
                ROOT / "components" / bootstrap.COMPONENT, root / "components" / bootstrap.COMPONENT
            )
            commands = []

            def terraform(command, **kwargs):
                commands.append(command)
                if command[0] == "git":
                    return "synthetic-test-commit\n"
                self.assertEqual(command[0], "terraform")
                self.assertNotIn("apply", command)
                self.assertNotIn("destroy", command)
                if command[1] == "plan":
                    (kwargs["cwd"] / "review.tfplan").write_bytes(b"synthetic-test-plan")
                if command[1] == "show":
                    kwargs["stdout"].write(json.dumps(self.fixture_plan()))
                return subprocess.CompletedProcess(command, 0)

            previous_umask = os.umask(0o077)
            try:
                with (
                    patch.object(bootstrap, "ROOT", root),
                    patch.object(bootstrap, "aws", side_effect=self.fake_aws),
                    patch.object(bootstrap.subprocess, "run", side_effect=terraform),
                    patch(
                        "evidence.subprocess.check_output", return_value="synthetic-test-commit\n"
                    ),
                ):
                    work = bootstrap.plan_bootstrap(self.env)
            finally:
                os.umask(previous_umask)
            self.assertEqual([c[1] for c in commands], ["init", "validate", "plan", "show"])
            self.assertNotIn("ssm", [c[0] for c in self.discovery_calls])
            self.assertIn('backend "local"', (work / "bootstrap_override.tf").read_text())
            self.assertEqual(work.stat().st_mode & 0o777, 0o700)
            self.assertTrue((work / "evidence/evidence.json").is_file())
            self.assertTrue((work / "plan.json").is_file())
