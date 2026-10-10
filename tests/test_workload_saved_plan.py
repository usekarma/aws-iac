"""Synthetic bundles and mocked cloud/process calls; never execute a real apply."""

import copy
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import workload_saved_plan as workload
from postflight import check_artifact_bucket


REPO = workload.ROOT


def env(apply=False):
    return {
        "AGENT_MODE": "0",
        "AWS_PROFILE": "strall-dev" if apply else "strall-dev-plan",
        "AWS_REGION": "us-east-1",
        "EXPECTED_AWS_ACCOUNT": workload.ACCOUNT,
        "EXPECTED_ENVIRONMENT": "dev",
        "EXPECTED_BINDING": "strall-com-dev",
        "IAC_PREFIX": "/iac",
        "AWS_MUTATION_APPROVED": "1" if apply else "0",
    }


def plan():
    after = {
        "aws_s3_bucket.s3_bucket": {
            "bucket": workload.BUCKET,
            "force_destroy": False,
            "tags": json.loads((REPO / workload.DECLARATION).read_text())["tags"]
            | {"Component": workload.COMPONENT},
        },
        "aws_s3_bucket_ownership_controls.ownership[0]": {
            "rule": [{"object_ownership": "BucketOwnerEnforced"}]
        },
        "aws_s3_bucket_public_access_block.block[0]": {k: True for k in workload.PUBLIC},
        "aws_s3_bucket_server_side_encryption_configuration.sse[0]": {
            "bucket": workload.BUCKET,
            "rule": [{"apply_server_side_encryption_by_default": [{"sse_algorithm": "AES256"}]}],
        },
        "aws_s3_bucket_versioning.versioning": {
            "versioning_configuration": [{"status": "Enabled"}]
        },
        "aws_ssm_parameter.runtime": {
            "name": workload.RUNTIME,
            "type": "String",
            "value": json.dumps({"bucket_name": workload.BUCKET}),
        },
    }
    return {
        "format_version": "1.2",
        "terraform_version": "1.15.2",
        "complete": True,
        "variables": {
            k: {"value": v}
            for k, v in {
                "component_name": workload.COMPONENT,
                "nickname": workload.NICKNAME,
                "region": "us-east-1",
                "iac_prefix": "/iac",
                "plan_config_json": None,
            }.items()
        },
        "resource_changes": [
            {
                "address": addr,
                "mode": "managed",
                "type": addr.split(".")[0],
                "provider_name": "registry.terraform.io/hashicorp/aws",
                "change": {"actions": ["create"], "before": None, "after": values},
            }
            for addr, values in after.items()
        ],
    }


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint((number << 3) | 2) + varint(len(value)) + value


class WorkloadTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(workload, "ROOT", self.root))
        for name in workload.INPUTS:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((REPO / name).read_bytes())
        self.work = (
            self.root
            / ".terragrunt-work"
            / workload.ACCOUNT
            / workload.COMPONENT
            / workload.NICKNAME
            / ".terragrunt-cache/a/b/components/s3-bucket"
        )
        self.work.mkdir(parents=True)
        for name in ("header.tf", "main.tf", "outputs.tf"):
            (self.work / name).write_bytes((REPO / "components/s3-bucket" / name).read_bytes())
        (self.work / "terragrunt.hcl").write_bytes((REPO / "terragrunt.hcl").read_bytes())
        self.wrapper = self.work.parents[4] / "terragrunt.hcl"
        self.wrapper.write_bytes((REPO / "terragrunt.hcl").read_bytes())
        (self.work / ".terraform/providers/test").mkdir(parents=True)
        (self.work / ".terraform/providers/test/terraform-provider-aws").write_text(
            "synthetic provider"
        )
        (self.work / ".terraform.lock.hcl").write_text("synthetic lock")
        self.backend = workload.BACKEND | {"profile": None}
        workload.write(
            self.work / ".terraform/terraform.tfstate",
            {"backend": {"type": "s3", "config": self.backend}},
        )
        self.live = {
            "config": {
                "Name": workload.CONFIG,
                "Type": "String",
                "Version": 1,
                "Value": (REPO / workload.DECLARATION).read_text(),
            },
            "config_sha256": "synthetic",
            "binding": {
                "Name": "/iac/environment",
                "Type": "String",
                "Version": 1,
                "Value": '{"name":"strall-com-dev","environment":"dev"}',
            },
            "state": {"present": False},
            "state_digest_item": {},
        }
        self.archived_state = {
            "resources": [
                {
                    "mode": "data",
                    "type": "aws_ssm_parameter",
                    "name": "config",
                    "instances": [
                        {
                            "attributes": {
                                "name": workload.CONFIG,
                                "type": "String",
                                "version": 1,
                                "value": self.live["config"]["Value"],
                            }
                        }
                    ],
                }
            ]
        }
        self.make_archive()
        self.json = plan()
        self.commands = []
        self.tool = self.root / "terraform-binary"
        self.tool.write_text("synthetic terraform")
        self.stack.enter_context(
            patch.object(workload.shutil, "which", return_value=str(self.tool))
        )
        self.stack.enter_context(
            patch.object(workload.subprocess, "check_output", return_value="a" * 40)
        )
        self.stack.enter_context(
            patch.object(workload.subprocess, "run", side_effect=self.run_command)
        )
        self.stack.enter_context(
            patch.object(workload, "snapshot", side_effect=lambda _: copy.deepcopy(self.live))
        )
        self.stack.enter_context(patch.object(workload, "aws", side_effect=self.caller))

    def caller(self, environment, *args):
        self.assertEqual(args, ("sts", "get-caller-identity"))
        role = (
            "IaCPlanReadOnly"
            if environment["AWS_PROFILE"] == "strall-dev-plan"
            else "AdministratorAccess"
        )
        return {
            "Account": workload.ACCOUNT,
            "Arn": f"arn:aws:sts::{workload.ACCOUNT}:assumed-role/AWSReservedSSO_{role}_abc/human",
        }

    def run_command(self, args, **kwargs):
        self.commands.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(self.json) if args[:3] == ["terraform", "show", "-json"] else "",
            stderr="",
        )

    def make_archive(self, backend=None, extra_source=False):
        be = (
            field(1, b"s3")
            + field(2, field(1, workload.backend_msgpack(backend or self.backend)))
            + field(3, b"default")
        )
        with zipfile.ZipFile(self.work / "review.tfplan", "w") as archive:
            archive.writestr("tfplan", field(1, 3) + field(14, b"1.15.2") + field(13, be))
            archive.writestr("tfstate", json.dumps(self.archived_state))
            archive.writestr("tfstate-prev", '{"resources":[]}')
            for name in ("header.tf", "main.tf", "outputs.tf"):
                archive.writestr("tfconfig/m-/" + name, (self.work / name).read_bytes())
            if extra_source:
                archive.writestr("tfconfig/m-/override.tf", "malicious")
            archive.writestr(
                ".terraform.lock.hcl", (self.work / ".terraform.lock.hcl").read_bytes()
            )

    def seal(self):
        out = workload.seal(env(), self.work)
        return out, workload.sha(out / "manifest.json")

    def assert_no_apply(self):
        self.assertFalse(any(args[:2] == ["terraform", "apply"] for args, _ in self.commands))

    def test_human_saved_plan_only_no_init_replan_new_state(self):
        out, digest = self.seal()
        with patch.object(workload, "postflight", return_value={"status": "verified"}):
            workload.apply_saved(env(True), out, digest)
        applies = [(a, kw) for a, kw in self.commands if a[:2] == ["terraform", "apply"]]
        self.assertEqual(len(applies), 1)
        self.assertEqual(
            applies[0][0],
            ["terraform", "apply", "-input=false", "-no-color", str(out / "review.tfplan")],
        )
        self.assertEqual(applies[0][1]["cwd"], self.work)
        self.assertEqual(applies[0][1]["env"]["AWS_PROFILE"], "strall-dev")
        self.assertFalse(
            any(
                a[0] == "terragrunt" or a[:2] in (["terraform", "init"], ["terraform", "plan"])
                for a, _ in self.commands
            )
        )
        self.assertFalse(list(out.glob("*.tfstate")))
        self.assertFalse((self.work / "terraform.tfstate").exists())
        self.assertEqual(workload.load(out / "manifest.json")["workspace"], str(self.work))
        with self.assertRaisesRegex(ValueError, "already attempted"):
            workload.apply_saved(env(True), out, digest)

    def test_agent_and_missing_explicit_mode_stop_before_discovery(self):
        for mode in ("1", None, "", "false"):
            for applying in (False, True):
                candidate = env(applying)
                candidate["AGENT_MODE"] = mode
                with (
                    self.subTest(mode=mode, applying=applying),
                    self.assertRaisesRegex(ValueError, "Human-only"),
                ):
                    workload.guard(candidate, applying)
        self.assertEqual(self.commands, [])

    def test_mutation_approval_required(self):
        candidate = env(True) | {"AWS_MUTATION_APPROVED": "0"}
        with self.assertRaisesRegex(ValueError, "AWS_MUTATION_APPROVED"):
            workload.apply_saved(candidate, "missing", "wrong")
        self.assertEqual(self.commands, [])

    def test_wrong_profile_account_binding_region_and_overrides_stop(self):
        for key, value in (
            ("AWS_PROFILE", "strall-dev-plan"),
            ("EXPECTED_AWS_ACCOUNT", "835990279085"),
            ("EXPECTED_BINDING", "prod"),
            ("EXPECTED_ENVIRONMENT", "prod"),
            ("AWS_REGION", "us-west-2"),
            ("IAC_PREFIX", "/other"),
            ("TF_CLI_ARGS_apply", "-auto-approve"),
            ("AWS_CONFIG_FILE", "/tmp/other"),
            ("AWS_ACCESS_KEY_ID", "synthetic"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                workload.guard(env(True) | {key: value}, True)

    def test_wrong_live_account_or_role_stop(self):
        for account, role, restricted in (
            ("835990279085", "IaCPlanReadOnly", True),
            (workload.ACCOUNT, "AdministratorAccess", True),
            (workload.ACCOUNT, "IaCPlanReadOnly", False),
            (workload.ACCOUNT, "ReadOnlyAccess", False),
        ):
            with (
                patch.object(
                    workload,
                    "aws",
                    return_value={
                        "Account": account,
                        "Arn": f"arn:aws:sts::{account}:assumed-role/AWSReservedSSO_{role}_abc/session",
                    },
                ),
                self.subTest(role=role),
                self.assertRaises(ValueError),
            ):
                workload.identity(env(), restricted)

    def test_wrong_independent_digest_stops_before_aws(self):
        out, _ = self.seal()
        with (
            patch.object(workload, "aws") as cloud,
            self.assertRaisesRegex(ValueError, "digest mismatch"),
        ):
            workload.apply_saved(env(True), out, "0" * 64)
        cloud.assert_not_called()
        self.assert_no_apply()

    def test_sealed_file_drifts_stop(self):
        out, digest = self.seal()
        files = [
            self.root / "components/s3-bucket/main.tf",
            self.root / workload.DECLARATION,
            self.root / "terragrunt.hcl",
            self.wrapper,
            self.work / ".terraform/terraform.tfstate",
            self.work / ".terraform.lock.hcl",
            self.work / "review.tfplan",
            out / "review.tfplan",
            out / "plan.json",
            out / "snapshot.json",
            self.tool,
            self.work / ".terraform/providers/test/terraform-provider-aws",
        ]
        for path in files:
            before = path.read_bytes()
            try:
                path.write_bytes(before + b"\nchanged")
                with self.subTest(file=str(path)), self.assertRaises((ValueError, KeyError)):
                    workload.apply_saved(env(True), out, digest)
                self.assert_no_apply()
            finally:
                path.write_bytes(before)

    def test_remote_config_state_and_binding_drifts_stop(self):
        out, digest = self.seal()
        for key in ("config", "binding", "state", "state_digest_item"):
            before = copy.deepcopy(self.live)
            self.live[key] = {"changed": True}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "changed after seal"):
                workload.apply_saved(env(True), out, digest)
            self.live = before
        self.assert_no_apply()

    def test_binary_export_json_mismatch_stops(self):
        out, digest = self.seal()
        self.json["terraform_version"] = "different"
        with self.assertRaisesRegex(ValueError, "reviewed JSON"):
            workload.apply_saved(env(True), out, digest)
        self.assert_no_apply()

    def test_archived_config_version_value_source_and_backend_must_match(self):
        for key, value in (("version", 2), ("value", "{}"), ("name", "/unrelated")):
            archived = copy.deepcopy(self.archived_state)
            self.archived_state["resources"][0]["instances"][0]["attributes"][key] = value
            self.make_archive()
            with self.subTest(key=key), self.assertRaises(ValueError):
                workload.validate_archive(
                    self.work, self.work / "review.tfplan", self.backend, self.live
                )
            self.archived_state = archived
        self.make_archive(self.backend | {"key": "unrelated.tfstate"})
        with self.assertRaisesRegex(ValueError, "backend differs"):
            workload.validate_archive(
                self.work, self.work / "review.tfplan", self.backend, self.live
            )
        self.make_archive(extra_source=True)
        with self.assertRaisesRegex(ValueError, "source inventory"):
            workload.validate_archive(
                self.work, self.work / "review.tfplan", self.backend, self.live
            )

    def test_override_plan_not_eligible(self):
        self.json["variables"]["plan_config_json"]["value"] = "{}"
        with self.assertRaisesRegex(ValueError, "normal SSM-backed"):
            workload.validate_plan(self.json)

    def test_no_local_or_second_state_owner_or_extra_source(self):
        for name in (
            "terraform.tfstate",
            ".terraform/environment",
            "extra.tf",
            "unreviewed.auto.tfvars.json",
        ):
            path = self.work / name
            path.write_text("{}")
            with self.subTest(name=name), self.assertRaises(ValueError):
                workload.workspace(self.work)
            path.unlink()
        with self.assertRaisesRegex(ValueError, "existing initialized"):
            workload.workspace(self.root)

    def test_actions_and_unexpected_resources_stop(self):
        for actions in (
            ["update"],
            ["delete"],
            ["delete", "create"],
            ["create", "delete"],
            ["no-op"],
            ["forget"],
        ):
            candidate = plan()
            candidate["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                workload.validate_plan(candidate)
        for count in (5, 7):
            candidate = plan()
            candidate["resource_changes"] = (
                candidate["resource_changes"][:count]
                if count == 5
                else candidate["resource_changes"]
                + [copy.deepcopy(candidate["resource_changes"][0])]
            )
            with self.subTest(count=count), self.assertRaises(ValueError):
                workload.validate_plan(candidate)
        candidate = plan()
        candidate["resource_changes"][0]["address"] = "aws_s3_bucket.unrelated"
        with self.assertRaises(ValueError):
            workload.validate_plan(candidate)

    def test_plan_bucket_security_values_stop(self):
        for addr, key, value in (
            ("aws_s3_bucket.s3_bucket", "force_destroy", True),
            ("aws_s3_bucket.s3_bucket", "website", [{"index_document": "index.html"}]),
            ("aws_s3_bucket_public_access_block.block[0]", "block_public_policy", False),
            (
                "aws_s3_bucket_versioning.versioning",
                "versioning_configuration",
                [{"status": "Suspended"}],
            ),
            (
                "aws_s3_bucket_ownership_controls.ownership[0]",
                "rule",
                [{"object_ownership": "ObjectWriter"}],
            ),
            ("aws_ssm_parameter.runtime", "name", "/unrelated"),
        ):
            candidate = plan()
            next(r for r in candidate["resource_changes"] if r["address"] == addr)["change"][
                "after"
            ][key] = value
            with self.subTest(addr=addr, key=key), self.assertRaises(ValueError):
                workload.validate_plan(candidate)

    def test_failure_never_retries_or_rolls_back(self):
        out, digest = self.seal()
        original_run = self.run_command

        def fail_apply(args, **kwargs):
            result = original_run(args, **kwargs)
            result.returncode = 1 if args[:2] == ["terraform", "apply"] else 0
            return result

        with (
            patch.object(workload.subprocess, "run", side_effect=fail_apply),
            self.assertRaisesRegex(ValueError, "partial"),
        ):
            workload.apply_saved(env(True), out, digest)
        self.assertEqual(
            workload.load(out / "post-apply.json")["status"], "apply-failed-may-be-partial"
        )
        with self.assertRaisesRegex(ValueError, "already attempted"):
            workload.apply_saved(env(True), out, digest)
        self.assertEqual(sum(a[:2] == ["terraform", "apply"] for a, _ in self.commands), 1)

    def test_postflight_failure_is_recorded(self):
        out, digest = self.seal()
        with (
            patch.object(workload, "postflight", side_effect=ValueError("security mismatch")),
            self.assertRaisesRegex(ValueError, "security mismatch"),
        ):
            workload.apply_saved(env(True), out, digest)
        self.assertEqual(workload.load(out / "post-apply.json")["status"], "postflight-failed")

    def test_other_components_nicknames_and_replan_arguments_rejected(self):
        for args in (
            ["seal", "lambda", workload.NICKNAME],
            ["apply", workload.COMPONENT, "unrelated"],
            ["apply", workload.COMPONENT, workload.NICKNAME, "--plan-dir", str(self.work)],
            ["plan", workload.COMPONENT, workload.NICKNAME],
        ):
            with (
                patch("sys.argv", ["workload_saved_plan.py", *args]),
                patch.object(workload, "apply_saved") as apply,
                patch.object(workload, "seal") as seal,
                patch("sys.stderr"),
                self.assertRaises(SystemExit),
            ):
                workload.main()
            apply.assert_not_called()
            seal.assert_not_called()

    def test_declaration_before_seal_and_backend_credentials_rejected(self):
        config_path = self.root / workload.DECLARATION
        config = workload.load(config_path)
        config["force_destroy"] = True
        config_path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            workload.declaration()
        backend_path = self.work / ".terraform/terraform.tfstate"
        metadata = workload.load(backend_path)
        metadata["backend"]["config"]["profile"] = "strall-dev-plan"
        backend_path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, "Backend identity"):
            workload.workspace(self.work)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.binding = {
            "Name": "/iac/environment",
            "Type": "String",
            "Version": 1,
            "Value": '{"name":"strall-com-dev","environment":"dev"}',
        }
        self.config = {
            "Name": workload.CONFIG,
            "Type": "String",
            "Version": 1,
            "Value": (REPO / workload.DECLARATION).read_text(),
        }
        self.calls = []

    def read(self, environment, *args):
        self.calls.append(args)
        if args[:2] == ("ssm", "get-parameter"):
            name = args[3]
            if name == workload.RUNTIME:
                raise workload.ReadError(
                    "(ParameterNotFound) when calling the GetParameter operation"
                )
            return {"Parameter": self.binding if name == "/iac/environment" else self.config}
        if args[:2] == ("s3api", "get-bucket-location"):
            raise workload.ReadError("(NoSuchBucket) when calling the GetBucketLocation operation")
        if args[:2] == ("dynamodb", "get-item"):
            self.assertEqual(
                json.loads(args[5]),
                {"LockID": {"S": workload.BACKEND["bucket"] + "/" + workload.KEY + "-md5"}},
            )
            return {}
        raise AssertionError("Unexpected API " + str(args[:2]))

    def test_snapshot_reads_only_exact_published_paths_and_backend(self):
        with (
            patch.object(workload, "aws", side_effect=self.read),
            patch.object(workload, "remote_state", return_value=({"present": False}, None)),
        ):
            result = workload.snapshot(env())
        self.assertEqual(result["config"]["Value"], self.config["Value"])
        self.assertEqual(result["state"], {"present": False})
        self.assertEqual(
            {a[:2] for a in self.calls},
            {("ssm", "get-parameter"), ("s3api", "get-bucket-location"), ("dynamodb", "get-item")},
        )

    def test_snapshot_rejects_wrong_binding_config_and_owned_state(self):
        with (
            patch.object(workload, "aws", side_effect=self.read),
            patch.object(workload, "remote_state", return_value=({"present": False}, None)),
        ):
            self.binding["Value"] = '{"name":"unrelated","environment":"dev"}'
            with self.assertRaisesRegex(ValueError, "binding mismatch"):
                workload.snapshot(env())
            self.binding["Value"] = '{"name":"strall-com-dev","environment":"dev"}'
            self.config["Value"] = "{}"
            with self.assertRaisesRegex(ValueError, "config differs"):
                workload.snapshot(env())
            self.config["Value"] = (REPO / workload.DECLARATION).read_text()
            with (
                patch.object(
                    workload,
                    "remote_state",
                    return_value=({"present": True}, {"resources": [{"mode": "managed"}]}),
                ),
                self.assertRaisesRegex(ValueError, "pre-existing"),
            ):
                workload.snapshot(env())

    def test_absence_accepts_only_exact_service_not_found_not_denial(self):
        for code in ("AccessDenied", "NoSuchBucket", "ParameterNotFoundAndSomethingElse"):
            with (
                patch.object(
                    workload,
                    "aws",
                    side_effect=workload.ReadError(f"({code}) when calling operation"),
                ),
                self.subTest(code=code),
                self.assertRaises(workload.ReadError),
            ):
                workload.absent(
                    env(), "ParameterNotFound", ("ssm", "get-parameter"), "--name", workload.RUNTIME
                )
        with (
            patch.object(workload, "aws", return_value={}),
            self.assertRaisesRegex(ValueError, "already exists"),
        ):
            workload.absent(
                env(), "ParameterNotFound", ("ssm", "get-parameter"), "--name", workload.RUNTIME
            )

    def test_state_read_absence_is_only_no_such_key(self):
        with patch.object(
            workload,
            "aws",
            side_effect=workload.ReadError("(NoSuchKey) when calling the GetObject operation"),
        ):
            self.assertEqual(workload.remote_state(env()), ({"present": False}, None))
        for code in ("AccessDenied", "NoSuchBucket"):
            with (
                patch.object(
                    workload,
                    "aws",
                    side_effect=workload.ReadError(
                        f"({code}) when calling the GetObject operation"
                    ),
                ),
                self.subTest(code=code),
                self.assertRaises(workload.ReadError),
            ):
                workload.remote_state(env())


class PostflightTest(unittest.TestCase):
    def setUp(self):
        self.answers = {
            "head-bucket": {},
            "get-bucket-location": {"LocationConstraint": None},
            "get-bucket-versioning": {"Status": "Enabled"},
            "get-bucket-ownership-controls": {
                "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}
            },
            "get-public-access-block": {
                "PublicAccessBlockConfiguration": {
                    k: True
                    for k in (
                        "BlockPublicAcls",
                        "BlockPublicPolicy",
                        "IgnorePublicAcls",
                        "RestrictPublicBuckets",
                    )
                }
            },
            "get-bucket-encryption": {
                "ServerSideEncryptionConfiguration": {
                    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
                }
            },
            "get-parameter": {
                "Parameter": {
                    "Name": workload.RUNTIME,
                    "Type": "String",
                    "Value": json.dumps({"bucket_name": workload.BUCKET}),
                }
            },
        }
        self.errors = {
            "get-bucket-website": "NoSuchWebsiteConfiguration",
            "get-bucket-policy": "NoSuchBucketPolicy",
            "get-bucket-lifecycle-configuration": "NoSuchLifecycleConfiguration",
        }

    def read(self, *args):
        if args[1] in self.errors:
            raise workload.ReadError(f"({self.errors[args[1]]}) when calling read operation")
        return self.answers[args[1]]

    def test_exact_bucket_and_runtime_pass(self):
        self.assertTrue(check_artifact_bucket(self.read))

    def test_security_region_and_runtime_mismatches_fail(self):
        for operation, bad in (
            ("get-bucket-location", {"LocationConstraint": "us-west-2"}),
            ("get-bucket-versioning", {"Status": "Suspended"}),
            ("get-bucket-ownership-controls", {"OwnershipControls": {"Rules": []}}),
            ("get-public-access-block", {"PublicAccessBlockConfiguration": {}}),
            (
                "get-bucket-encryption",
                {
                    "ServerSideEncryptionConfiguration": {
                        "Rules": [
                            {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}
                        ]
                    }
                },
            ),
            (
                "get-parameter",
                {"Parameter": {"Name": workload.RUNTIME, "Type": "String", "Value": "{}"}},
            ),
        ):
            previous = self.answers[operation]
            self.answers[operation] = bad
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                check_artifact_bucket(self.read)
            self.answers[operation] = previous

    def test_missing_runtime_and_access_denied_are_failures(self):
        for error in ("ParameterNotFound", "AccessDenied"):
            self.errors["get-parameter"] = error
            with self.subTest(error=error), self.assertRaises(workload.ReadError):
                check_artifact_bucket(self.read)

    def test_website_policy_lifecycle_are_absent_not_denied(self):
        for operation in list(self.errors):
            error = self.errors.pop(operation)
            self.answers[operation] = {}
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                check_artifact_bucket(self.read)
            self.errors[operation] = "AccessDenied"
            with self.assertRaises(workload.ReadError):
                check_artifact_bucket(self.read)
            self.errors[operation] = error

    def test_postflight_state_must_own_exactly_reviewed_six(self):
        resources = []
        for address in workload.EXPECTED:
            kind, name = address.split(".")
            instance = {"attributes": {}}
            if name.endswith("[0]"):
                name = name[:-3]
                instance["index_key"] = 0
            resources.append(
                {"mode": "managed", "type": kind, "name": name, "instances": [instance]}
            )
        state = {"resources": resources}
        with (
            patch.object(workload, "identity"),
            patch.object(workload, "aws", side_effect=lambda _, *args: self.read(*args)),
            patch.object(workload, "remote_state", return_value=({"present": True}, state)),
        ):
            self.assertEqual(workload.postflight(env(True))["status"], "verified")
            state["resources"].append(
                {
                    "mode": "managed",
                    "type": "aws_lambda_function",
                    "name": "unrelated",
                    "instances": [{"attributes": {}}],
                }
            )
            with self.assertRaisesRegex(ValueError, "scope differs"):
                workload.postflight(env(True))


if __name__ == "__main__":
    unittest.main()
