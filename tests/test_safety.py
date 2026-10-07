"""Behavioral tests of approval/identity boundaries, with no AWS connectivity."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ShellSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        # Isolate all command-created artifacts from the real repository.
        import shutil

        shutil.copytree(ROOT / "scripts", self.work / "scripts")
        if (ROOT / "components").exists():
            (self.work / "components/clickhouse").mkdir(parents=True)
            (self.work / "components/clickhouse/header.tf").write_text(
                'terraform { backend "s3" {} }'
            )
            shutil.copy(ROOT / "terragrunt.hcl", self.work / "terragrunt.hcl")
        (self.work / "bin").mkdir()
        self.log = self.work / "calls.jsonl"
        fake = (
            "#!/usr/bin/env python3\n"
            + """
import json, os, sys
from pathlib import Path
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
if Path(sys.argv[0]).name == "aws":
    if "get-caller-identity" in sys.argv:
        print(os.environ.get("MOCK_ACCOUNT", "123456789012"))
    elif "get-parameter" in sys.argv:
        print(json.dumps({"name": os.environ.get("MOCK_BINDING", "usekarma-dev-prod"), "environment": os.environ.get("MOCK_ENV", "prod")}))
    elif "head-bucket" in sys.argv and os.environ.get("MOCK_BACKEND_MISSING"):
        sys.exit(1)
"""
        )
        for name in ("aws", "terragrunt"):
            path = self.work / "bin" / name
            path.write_text(fake)
            path.chmod(0o755)
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TG_", "EXPECTED_"))
        }
        self.env.update(
            PATH=str(self.work / "bin") + os.pathsep + os.environ["PATH"],
            MOCK_LOG=str(self.log),
            AWS_PROFILE="prod-karma",
            AWS_REGION="us-east-1",
            EXPECTED_AWS_ACCOUNT="123456789012",
            EXPECTED_ENVIRONMENT="prod",
            EXPECTED_BINDING="usekarma-dev-prod",
        )

    def call(self, script, *args, **env):
        return subprocess.run(
            ["bash", str(self.work / "scripts" / script), *args],
            env=self.env | env,
            capture_output=True,
            text=True,
        )

    def calls(self):
        return (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )

    def test_agent_mode_blocks_mutations_even_with_approval(self):
        for args in (
            ("clickhouse", "usekarma-dev"),
            ("clickhouse", "usekarma-dev", "-d"),
            ("--plan", "clickhouse", "usekarma-dev", "--auto-approve"),
        ):
            result = self.call("deploy.sh", *args, AGENT_MODE="1", AWS_MUTATION_APPROVED="1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_MODE", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_agent_mode_blocks_backend_and_local_state_cleanup(self):
        for script in ("bootstrap/remote_state.sh", "clean.sh"):
            result = self.call(
                script, AGENT_MODE="1", AWS_MUTATION_APPROVED="1", LOCAL_STATE_CLEANUP_APPROVED="1"
            )
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_component_publish_and_cleanup_entrypoints_block_agent_mode(self):
        scripts = (
            "components/clickhouse/logout-image/build.sh",
            "components/clickhouse/kconnect-metrics-image/build.sh",
            "components/clickhouse/clickhouse-ami/scripts/clean-old-ami.sh",
        )
        for script in scripts:
            result = subprocess.run(
                ["bash", str(ROOT / script)],
                env=self.env
                | {
                    "AGENT_MODE": "1",
                    "AWS_MUTATION_APPROVED": "1",
                    "AWS_DESTRUCTIVE_APPROVED": "1",
                },
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Agent mode", result.stderr)
        result = subprocess.run(
            ["make", "-C", str(ROOT / "components/clickhouse/clickhouse-ami"), "clickhouse"],
            env=self.env | {"AGENT_MODE": "1", "AWS_MUTATION_APPROVED": "1"},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Agent mode", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_agent_mode_validate_allowed(self):
        result = self.call("deploy.sh", "--validate", "clickhouse", "usekarma-dev", AGENT_MODE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c[1] for c in self.calls() if c[0] == "terragrunt"], ["init", "validate"])

    def test_preflight_success_uses_explicit_profile_region(self):
        result = self.call("preflight.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 2)
        for call in self.calls():
            self.assertIn("--profile", call)
            self.assertIn("--region", call)

    def test_wrong_account_rejected_before_ssm(self):
        self.assertNotEqual(self.call("preflight.sh", MOCK_ACCOUNT="999999999999").returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_wrong_binding_or_environment_rejected(self):
        for key in ("MOCK_BINDING", "MOCK_ENV"):
            with self.subTest(key=key):
                self.assertNotEqual(self.call("preflight.sh", **{key: "wrong"}).returncode, 0)

    def test_competing_credentials_rejected_without_aws(self):
        self.assertNotEqual(self.call("preflight.sh", AWS_ACCESS_KEY_ID="synthetic").returncode, 0)
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless((ROOT / "terragrunt.hcl").exists(), "IaC entrypoint only")
    def test_unapproved_apply_and_destroy_rejected_without_aws(self):
        for args in (("clickhouse", "usekarma-dev"), ("clickhouse", "usekarma-dev", "-d")):
            self.assertNotEqual(self.call("deploy.sh", *args).returncode, 0)
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless((ROOT / "terragrunt.hcl").exists(), "IaC entrypoint only")
    def test_destroy_plan_cannot_execute_destroy_or_bootstrap(self):
        result = self.call(
            "plan.sh",
            "clickhouse",
            "usekarma-dev",
            "--destroy",
            TG_BACKEND_BOOTSTRAP="true",
            TG_ALL="true",
            TG_NON_INTERACTIVE="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        tg = [call for call in self.calls() if call[0] == "terragrunt"]
        self.assertEqual([call[1] for call in tg], ["init", "plan"])
        self.assertIn("-destroy", tg[-1])
        self.assertIn("-lock=false", tg[-1])
        for call in tg:
            self.assertNotIn("--all", call)
            self.assertIn("--backend-require-bootstrap", call)
            self.assertIn("--disable-bucket-update", call)
            self.assertNotIn("--backend-bootstrap", call)

    @unittest.skipUnless((ROOT / "terragrunt.hcl").exists(), "IaC entrypoint only")
    def test_wrong_target_and_missing_backend_stop_before_terragrunt(self):
        for env in ({"MOCK_ACCOUNT": "999999999999"}, {"MOCK_BACKEND_MISSING": "1"}):
            result = self.call("plan.sh", "clickhouse", "usekarma-dev", **env)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == "terragrunt" for c in self.calls()))

    @unittest.skipUnless((ROOT / "terragrunt.hcl").exists(), "IaC entrypoint only")
    def test_plan_rejects_mutation_flags(self):
        self.assertNotEqual(
            self.call("plan.sh", "clickhouse", "usekarma-dev", "--auto-approve").returncode, 0
        )
        self.assertNotEqual(
            self.call(
                "deploy.sh", "--plan", "clickhouse", "usekarma-dev", "--auto-approve"
            ).returncode,
            0,
        )
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless((ROOT / "terragrunt.hcl").exists(), "IaC entrypoint only")
    def test_identity_and_terraform_argument_overrides_stop_before_terragrunt(self):
        for env in ({"TG_IAM_ASSUME_ROLE": "synthetic-role"}, {"TF_CLI_ARGS_plan": "-destroy"}):
            self.assertNotEqual(
                self.call("plan.sh", "clickhouse", "usekarma-dev", **env).returncode, 0
            )
        self.assertFalse(any(c[0] == "terragrunt" for c in self.calls()))


class ConfigSafetyTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "scripts/mutation_guard.py").exists(), "config publisher only")
    def test_guard_identity_binding_and_approval(self):
        calls = []

        class Client:
            def get_caller_identity(self):
                calls.append("sts")
                return {"Account": os.environ.get("MOCK_ACCOUNT", "123456789012")}

            def get_parameter(self, **kwargs):
                calls.append("ssm-read")
                return {
                    "Parameter": {
                        "Value": json.dumps(
                            {
                                "name": "usekarma-dev-prod",
                                "environment": os.environ.get("MOCK_ENV", "prod"),
                            }
                        )
                    }
                }

        class Session:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def client(self, service):
                return Client()

        fake = types.SimpleNamespace(Session=Session)
        with patch.dict(sys.modules, {"boto3": fake}):
            spec = importlib.util.spec_from_file_location(
                "guard", ROOT / "scripts/mutation_guard.py"
            )
            guard = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(guard)
        env = dict(
            AWS_PROFILE="prod-karma",
            AWS_REGION="us-east-1",
            EXPECTED_AWS_ACCOUNT="123456789012",
            EXPECTED_ENVIRONMENT="prod",
            EXPECTED_BINDING="usekarma-dev-prod",
        )
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                guard.approved_session()
            self.assertEqual(calls, [])
            os.environ["AWS_MUTATION_APPROVED"] = "1"
            os.environ["MOCK_ACCOUNT"] = "999999999999"
            with self.assertRaises(SystemExit):
                guard.approved_session()
            self.assertNotIn("ssm-read", calls)
            del os.environ["MOCK_ACCOUNT"]
            os.environ["MOCK_ENV"] = "wrong"
            with self.assertRaises(SystemExit):
                guard.approved_session()
            del os.environ["MOCK_ENV"]
            guard.approved_session()
            self.assertIn({"profile_name": "prod-karma", "region_name": "us-east-1"}, calls)
            with self.assertRaises(SystemExit):
                guard.check_local_binding({"name": "wrong", "environment": "prod"})


class ConfigValidationTests(unittest.TestCase):
    def test_provider_validation_isolates_data_and_cli_overrides(self):
        spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify.py")
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        with tempfile.TemporaryDirectory() as temp:
            verify.ROOT = Path(temp)
            module = verify.ROOT / "components/vpc"
            module.mkdir(parents=True)
            (module / "main.tf").write_text("terraform {}")
            calls = []
            with patch.dict(
                os.environ, {"TF_DATA_DIR": "/unexpected", "TF_CLI_ARGS_init": "-backend=true"}
            ):
                with patch.object(
                    verify, "run", side_effect=lambda args, **kw: calls.append((args, kw))
                ):
                    verify.provider_validate("vpc")
            self.assertEqual(len(calls), 2)
            self.assertIn("-backend=false", calls[0][0])
            for args, kwargs in calls:
                self.assertNotIn("TF_CLI_ARGS_init", kwargs["env"])
                self.assertEqual(
                    kwargs["env"]["TF_DATA_DIR"], str(Path(kwargs["cwd"]) / ".terraform")
                )
                self.assertNotEqual(Path(kwargs["cwd"]), module)

    def test_duplicate_keys_and_binding_mismatch_fail(self):
        spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify.py")
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        with self.assertRaises(ValueError):
            json.loads('{"test":1,"test":2}', object_pairs_hook=verify.no_duplicates)
        with self.assertRaises(ValueError):
            verify.validate_config(Path("account_environments/wrong.json"), {"name": "different"})


if __name__ == "__main__":
    unittest.main()
