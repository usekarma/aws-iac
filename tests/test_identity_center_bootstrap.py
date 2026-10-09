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
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
bootstrap = importlib.import_module("bootstrap_identity_center")


class BootstrapApplyTests(unittest.TestCase):
    def setUp(self):
        BootstrapTests.setUp(self)
        self.env["AWS_MUTATION_APPROVED"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "examples").mkdir()
        shutil.copy(ROOT / bootstrap.DECLARATION, self.root / bootstrap.DECLARATION)
        shutil.copytree(
            ROOT / "components" / bootstrap.COMPONENT,
            self.root / "components" / bootstrap.COMPONENT,
        )
        (self.root / "scripts").mkdir()
        for name in ("bootstrap_identity_center.py", "evidence.py"):
            shutil.copy(ROOT / "scripts" / name, self.root / "scripts" / name)
        self.work = self.root / "artifacts/identity-center-bootstrap/review-test"
        self.work.mkdir(parents=True)
        for source in (self.root / "components" / bootstrap.COMPONENT).glob("*.tf"):
            shutil.copy(source, self.work / source.name)
        (self.work / "bootstrap_override.tf").write_text('terraform {\n  backend "local" {}\n}\n')
        (self.work / ".terraform.lock.hcl").write_text("synthetic-provider-lock\n")
        (self.work / ".terraform").mkdir()
        (self.work / ".terraform/terraform.tfstate").write_text(
            json.dumps(
                {"backend": {"type": "local", "config": {"path": None, "workspace_dir": None}}}
            )
        )
        self.variables = {
            "component_name": bootstrap.COMPONENT,
            "nickname": "owner-iac-plan-readonly",
            "region": "us-east-1",
            "administration_account_id": bootstrap.OWNER,
            "bootstrap_config_json": json.dumps(self.config),
        }
        (self.work / "bootstrap.tfvars.json").write_text(json.dumps(self.variables))
        self.plan = BootstrapTests.fixture_plan(self)
        self.plan["variables"] = {k: {"value": v} for k, v in self.variables.items()}
        context = json.loads((ROOT / "examples/review-context.synthetic.json").read_text())
        context.update(
            account=bootstrap.OWNER,
            profile=self.env["AWS_PROFILE"],
            region="us-east-1",
            component=bootstrap.COMPONENT,
            nickname="owner-iac-plan-readonly",
            synthetic=False,
        )
        (self.work / "context.json").write_text(json.dumps(context))
        (self.work / "discovery.json").write_text(json.dumps({"identity": self.identity}))
        self.rebuild_plan()
        self.calls = []
        self.postflight_calls = []
        for patcher in (
            patch.object(bootstrap, "ROOT", self.root),
            patch.object(
                bootstrap,
                "repository_identity",
                return_value={"name": "usekarma/aws-iac", "commit": "b" * 40},
            ),
            patch.object(bootstrap, "verify_ancestor"),
            patch.object(bootstrap.subprocess, "run", side_effect=self.terraform),
            patch.object(bootstrap, "aws", side_effect=self.fake_aws),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)

    def rebuild_plan(self):
        with zipfile.ZipFile(self.work / "review.tfplan", "w") as archive:
            for source in self.work.glob("*.tf"):
                archive.write(source, "tfconfig/m-/" + source.name)
            archive.write(self.work / ".terraform.lock.hcl", ".terraform.lock.hcl")
        (self.work / "plan.json").write_text(json.dumps(self.plan))
        evidence = {
            "repository_commit": "a" * 40,
            "source": {
                "synthetic": False,
                "saved_plan_sha256": bootstrap.sha256(self.work / "review.tfplan"),
                "plan_json_sha256": bootstrap.sha256(self.work / "plan.json"),
            },
            "context": json.loads((self.work / "context.json").read_text()),
        }
        (self.work / "evidence").mkdir(exist_ok=True)
        (self.work / "evidence/evidence.json").write_text(json.dumps(evidence))
        (self.work / "evidence/summary.md").write_text("Synthetic test review summary\n")

    def terraform(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(command[0], "terraform")
        self.assertNotIn("plan", command)
        self.assertNotIn("init", command)
        if command[1] == "show":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.plan))
        self.assertEqual(
            command, ["terraform", "apply", "-input=false", "-no-color", "review.tfplan"]
        )
        self.assertEqual(kwargs["cwd"], self.work)
        return subprocess.CompletedProcess(command, 0)

    def fake_aws(self, env, service, action, *args):
        if any(c[1] == "apply" for c in self.calls):
            self.postflight_calls.append(action)
            if action == "list-permission-sets":
                return {"PermissionSets": ["new"]}
            if action == "describe-permission-set":
                return {
                    "PermissionSet": {
                        "Name": "IaCPlanReadOnly",
                        "SessionDuration": "PT1H",
                        "PermissionSetArn": "new",
                    }
                }
            if action == "get-inline-policy-for-permission-set":
                return {"InlinePolicy": json.dumps(self.config["inline_policy"])}
            if action == "list-managed-policies-in-permission-set":
                return {"AttachedManagedPolicies": []}
            if action == "list-customer-managed-policy-references-in-permission-set":
                return {"CustomerManagedPolicyReferences": []}
            if action == "list-account-assignments":
                return {
                    "AccountAssignments": [
                        {
                            "AccountId": "623155450153",
                            "PrincipalType": "USER",
                            "PrincipalId": bootstrap.PRINCIPAL,
                        }
                    ]
                }
            self.fail("Unexpected postflight API: " + action)
        return BootstrapTests.fake_aws(self, env, service, action, *args)

    def seal(self):
        return bootstrap.seal_bundle(self.env, self.work)

    def assert_no_apply(self):
        self.assertFalse(any(c[1] == "apply" for c in self.calls))

    def test_apply_requires_both_approvals_and_rejects_agents(self):
        for overrides in (
            {"AGENT_MODE": "1"},
            {"HUMAN_BOOTSTRAP_APPROVED": ""},
            {"AWS_MUTATION_APPROVED": ""},
        ):
            with self.assertRaises(ValueError):
                bootstrap.apply_bootstrap(self.env | overrides, self.work, "f" * 64)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.discovery_calls, [])

    def test_rejects_missing_bundle_files_and_outside_directory(self):
        for name in (
            "review.tfplan",
            "plan.json",
            "context.json",
            "evidence/evidence.json",
            "evidence/summary.md",
        ):
            original = (self.work / name).read_bytes()
            (self.work / name).unlink()
            with self.assertRaises(ValueError):
                self.seal()
            (self.work / name).write_bytes(original)
        with self.assertRaises(ValueError):
            bootstrap.review_directory(self.root)
        self.assert_no_apply()

    def test_manifest_is_exclusive_and_altered_files_digest_or_code_rejected(self):
        digest = self.seal()
        with self.assertRaises(ValueError):
            self.seal()
        for name in (
            "review.tfplan",
            "plan.json",
            "context.json",
            "evidence/evidence.json",
            "evidence/summary.md",
            "bootstrap.tfvars.json",
            ".terraform/terraform.tfstate",
        ):
            original = (self.work / name).read_bytes()
            (self.work / name).write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                bootstrap.apply_bootstrap(self.env, self.work, digest)
            (self.work / name).write_bytes(original)
        with self.assertRaises(ValueError):
            bootstrap.apply_bootstrap(self.env, self.work, "0" * 64)
        (self.root / "scripts/bootstrap_identity_center.py").write_text("changed")
        with self.assertRaises(ValueError):
            bootstrap.apply_bootstrap(self.env, self.work, digest)
        self.assert_no_apply()

    def test_rejects_unsafe_plans_even_before_manifest_creation(self):
        good = copy.deepcopy(self.plan)
        for actions in (["update"], ["delete"], ["delete", "create"]):
            self.plan = copy.deepcopy(good)
            self.plan["resource_changes"][0]["change"]["actions"] = actions
            self.rebuild_plan()
            with self.assertRaises(ValueError):
                self.seal()
        changes = [
            (0, "name", "WrongName"),
            (0, "session_duration", "PT8H"),
            (2, "target_id", "835990279085"),
            (2, "principal_id", "wrong"),
            (2, "principal_type", "GROUP"),
            (1, "inline_policy", "{}"),
        ]
        for index, key, value in changes:
            self.plan = copy.deepcopy(good)
            self.plan["resource_changes"][index]["change"]["after"][key] = value
            self.rebuild_plan()
            with self.assertRaises(ValueError):
                self.seal()
        self.plan = copy.deepcopy(good)
        self.plan["resource_changes"].append(
            {
                "address": "aws_ssoadmin_managed_policy_attachment.admin",
                "type": "aws_ssoadmin_managed_policy_attachment",
                "change": {"actions": ["create"]},
            }
        )
        self.rebuild_plan()
        with self.assertRaises(ValueError):
            self.seal()
        self.assert_no_apply()

    def test_binary_export_mismatch_and_component_changes_rejected(self):
        self.plan["variables"]["nickname"]["value"] = "changed"
        with self.assertRaises(ValueError):
            self.seal()
        self.plan["variables"]["nickname"]["value"] = "owner-iac-plan-readonly"
        (self.root / "components" / bootstrap.COMPONENT / "main.tf").write_text("changed")
        with self.assertRaises(ValueError):
            self.seal()
        self.assert_no_apply()

    def test_wrong_live_account_or_existing_permission_set_prevents_apply(self):
        digest = self.seal()
        self.identity["Account"] = "623155450153"
        with self.assertRaises(ValueError):
            bootstrap.apply_bootstrap(self.env, self.work, digest)
        self.identity["Account"] = bootstrap.OWNER

        def existing(env, service, action, *args):
            if action == "describe-permission-set":
                return {"PermissionSet": {"Name": "IaCPlanReadOnly"}}
            return self.fake_aws(env, service, action, *args)

        with patch.object(bootstrap, "aws", side_effect=existing):
            with self.assertRaises(ValueError):
                bootstrap.apply_bootstrap(self.env, self.work, digest)
        self.assert_no_apply()

    def test_applies_only_saved_plan_and_verifies_postflight(self):
        digest = self.seal()
        bootstrap.apply_bootstrap(self.env, self.work, digest)
        self.assertEqual([c[1] for c in self.calls], ["show", "show", "apply"])
        self.assertEqual(
            json.loads((self.work / "post-apply.json").read_text())["status"], "verified"
        )
        self.assertIn("list-managed-policies-in-permission-set", self.postflight_calls)
        self.assertIn(
            "list-customer-managed-policy-references-in-permission-set", self.postflight_calls
        )

    def test_postflight_failure_is_recorded_without_automatic_retry(self):
        digest = self.seal()

        def unexpected_policy(env, service, action, *args):
            if action == "list-managed-policies-in-permission-set":
                return {"AttachedManagedPolicies": [{"Arn": "unreviewed"}]}
            return self.fake_aws(env, service, action, *args)

        with patch.object(bootstrap, "aws", side_effect=unexpected_policy):
            with self.assertRaises(ValueError):
                bootstrap.apply_bootstrap(self.env, self.work, digest)
        self.assertEqual(
            json.loads((self.work / "post-apply.json").read_text())["status"], "failed"
        )
        self.assertEqual(sum(c[1] == "apply" for c in self.calls), 1)


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

    def test_other_components_and_apply_without_review_are_not_callable(self):
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
