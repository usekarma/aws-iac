"""Fail-closed contracts using synthetic plans; no AWS or Terraform execution."""

import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import declarative_iam_maintenance as maintenance


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = self.root / "owner"
        self.review = self.root / "review"
        self.planning = self.root / "planning"
        for p in (self.owner, self.review, self.planning):
            p.mkdir()
        self.baseline = {
            "inline_policy": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "Baseline",
                        "Effect": "Allow",
                        "Action": "sts:GetCallerIdentity",
                        "Resource": "*",
                    }
                ],
            },
            "assignments": [{"target_account_id": a} for a in maintenance.ACCOUNTS],
        }
        self.additions = [
            {
                "Sid": "ExactRead",
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::example/exact",
            }
        ]
        before = {"inline_policy": json.dumps(self.baseline["inline_policy"]), "id": "policy"}
        after = before | {
            "inline_policy": json.dumps(
                self.baseline["inline_policy"]
                | {"Statement": self.baseline["inline_policy"]["Statement"] + self.additions}
            )
        }
        self.plan = {
            "resource_changes": [
                {
                    "mode": "managed",
                    "address": maintenance.ADDRESS,
                    "change": {"actions": ["update"], "before": before, "after": after},
                }
            ]
            + [
                {"mode": "managed", "address": f"resource.{i}", "change": {"actions": ["no-op"]}}
                for i in range(6)
            ]
        }
        resources = [
            {
                "mode": "managed",
                "type": "aws_ssoadmin_permission_set_inline_policy",
                "name": "inline_policy",
                "instances": [{"attributes": before}],
            }
        ] + [
            {
                "mode": "managed",
                "type": "resource",
                "name": str(i),
                "instances": [{"attributes": {"id": str(i)}}],
            }
            for i in range(6)
        ]
        self.state = {"serial": 20, "lineage": "lineage", "resources": resources}
        self.write(self.owner / "terraform.tfstate", self.state)
        (self.owner / ".terraform").mkdir()
        self.write(
            self.owner / ".terraform/terraform.tfstate",
            {"backend": {"type": "local", "config": {"path": None, "workspace_dir": None}}},
        )
        for name in ("main.tf", ".terraform.lock.hcl", "bootstrap.tfvars.json"):
            (self.owner / name).write_text("{}")
        for name in ("main.tf", ".terraform.lock.hcl", "terraform.tfstate"):
            (self.planning / name).write_bytes((self.owner / name).read_bytes())
        self.write(self.review / "plan.json", self.plan)
        self.write(self.review / "baseline.json", self.baseline)
        with zipfile.ZipFile(self.review / "review.tfplan", "w") as z:
            z.writestr("tfconfig/m-/main.tf", "{}")
            z.writestr(".terraform.lock.hcl", "{}")
        owner_hashes = {
            name: maintenance.digest(self.owner / name)
            for name in [
                "main.tf",
                ".terraform.lock.hcl",
                "bootstrap.tfvars.json",
                "terraform.tfstate",
                ".terraform/terraform.tfstate",
            ]
        }
        self.contract = {
            "contract": "declarative-iam-maintenance-v1",
            "owner_directory": str(self.owner),
            "review_directory": str(self.review),
            "planning_directory": str(self.planning),
            "state_serial": 20,
            "state_lineage": "lineage",
            "owner_hashes": owner_hashes,
            "baseline_file": "baseline.json",
            "additions": self.additions,
            "source_files": {"main.tf": maintenance.digest(self.owner / "main.tf")},
            "reprovisioning_accounts": maintenance.ACCOUNTS,
            "evidence_files": ["owner-context.json", "rollback.json"],
        }
        self.write(
            self.review / "owner-context.json",
            {
                "owner_directory": str(self.owner),
                "state_serial": 20,
                "state_lineage": "lineage",
                "owner_hashes": owner_hashes,
                "planning_directory": str(self.planning),
            },
        )
        self.write(
            self.review / "rollback.json",
            {
                "baseline": self.baseline,
                "automatic_rollback": False,
                "requires_new_plan_and_human_approval": True,
            },
        )
        self.contract["files"] = {p.name: maintenance.digest(p) for p in self.review.iterdir()}
        self.path = self.root / "contract.json"
        self.write(self.path, self.contract)
        self.addCleanup(patch.stopall)
        patch.object(maintenance, "OWNER", self.owner).start()
        self.run = patch.object(
            maintenance.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=json.dumps(self.plan)),
        ).start()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def test_valid_exact_delta(self):
        _, baseline, desired = maintenance.validate(self.path)
        self.assertEqual(baseline, self.baseline)
        self.assertEqual(desired["inline_policy"]["Statement"][-1], self.additions[0])
        self.assertEqual(self.run.call_args.kwargs["cwd"], self.planning)
        self.assertEqual(self.run.call_args.args[0][1:3], ["show", "-json"])

    def test_tampered_plan_and_missing_evidence(self):
        for name in ("review.tfplan", "owner-context.json", "rollback.json"):
            original = (self.review / name).read_bytes()
            (self.review / name).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                maintenance.validate(self.path)
            (self.review / name).write_bytes(original)
        self.contract["evidence_files"] = []
        self.write(self.path, self.contract)
        with self.assertRaises(ValueError):
            maintenance.validate(self.path)

    def test_stale_state_and_competing_owner(self):
        self.contract["state_serial"] = 19
        self.write(self.path, self.contract)
        with self.assertRaises(ValueError):
            maintenance.validate(self.path)
        self.contract["owner_directory"] = str(self.planning)
        self.write(self.path, self.contract)
        with self.assertRaises(ValueError):
            maintenance.validate(self.path)

    def test_unexpected_changes_and_replacements(self):
        for actions in (["create"], ["delete", "create"], ["delete"]):
            plan = copy.deepcopy(self.plan)
            plan["resource_changes"][0]["change"]["actions"] = actions
            with self.assertRaises(ValueError):
                maintenance.validate_plan(plan, self.baseline, self.additions)
        plan = copy.deepcopy(self.plan)
        plan["resource_changes"][1]["change"]["actions"] = ["update"]
        with self.assertRaises(ValueError):
            maintenance.validate_plan(plan, self.baseline, self.additions)
        with self.assertRaises(ValueError):
            maintenance.validate_plan(
                self.plan,
                self.baseline,
                self.additions
                + [{"Sid": "Extra", "Effect": "Allow", "Action": "*", "Resource": "*"}],
            )

    def test_binary_json_disagreement(self):
        self.run.return_value.stdout = "{}"
        with self.assertRaises(ValueError):
            maintenance.validate(self.path)

    def test_exclusive_attempt_never_overwrites(self):
        marker = self.root / "attempt.json"
        maintenance.exclusive(marker, {"status": "started"})
        with self.assertRaises(FileExistsError):
            maintenance.exclusive(marker, {"status": "retry"})
        self.assertEqual(maintenance.load(marker), {"status": "started"})

    def test_human_only_environment_and_approval(self):
        with patch.dict("os.environ", {"AGENT_MODE": "1"}, clear=True):
            with self.assertRaises(ValueError):
                maintenance.runtime.environment("apply")
        approval = self.root / "approval.json"
        self.write(approval, {"approved": False})
        with self.assertRaises(ValueError):
            maintenance.approved(approval, "seal", self.path)

    def test_failed_apply_uses_owner_and_cannot_retry(self):
        approval = {"owner_profile": "identity-center-admin"}
        manifest = self.review / "declarative-iam-manifest.json"
        seal_approval = self.review / "seal-approval.json"
        self.write(seal_approval, {})
        self.write(
            manifest,
            {
                "contract_sha256": maintenance.digest(self.path),
                "workflow_sha256": maintenance.workflow_hash(),
                "seal_approval_path": str(seal_approval),
                "seal_approval_sha256": maintenance.digest(seal_approval),
            },
        )
        args = []

        def fake_run(command, **kwargs):
            args.append((command, kwargs))
            return SimpleNamespace(returncode=1)

        with (
            patch.object(
                maintenance, "validate", return_value=(self.contract, self.baseline, self.baseline)
            ),
            patch.object(maintenance, "approved", return_value=approval),
            patch.object(maintenance.runtime, "environment", return_value={}),
            patch.object(maintenance, "live") as live,
            patch.object(maintenance.subprocess, "run", side_effect=fake_run),
        ):
            with self.assertRaisesRegex(ValueError, "Terraform failed"):
                maintenance.execute("apply", self.path, seal_approval)
            self.assertEqual(args[0][1]["cwd"], self.owner)
            self.assertEqual(args[0][0][1], "apply")
            self.assertTrue((self.review / "declarative-iam-attempt.json").exists())
            with self.assertRaises(FileExistsError):
                maintenance.execute("apply", self.path, seal_approval)
            self.assertEqual(len(args), 1)
            self.assertEqual(live.call_count, 2)  # preflight only, no postflight on failure

    def test_live_identity_failure_records_evidence(self):
        approval = {
            "owner_profile": "identity-center-admin",
            "target_read_profile": "m1-dev-operator",
            "owner_identity_arn": "expected-management-arn",
            "target_read_identity_arn": "expected-target-arn",
        }
        evidence = self.root / "live.json"
        with patch.object(
            maintenance.runtime, "aws", return_value={"Account": "wrong", "Arn": "wrong"}
        ):
            with self.assertRaisesRegex(ValueError, "Live identity"):
                maintenance.live({}, approval, self.baseline, evidence)
        self.assertEqual(len(maintenance.load(evidence)["calls"]), 1)

    def test_both_account_postflight_and_boundary_failure(self):
        approval = {
            "owner_profile": "identity-center-admin",
            "target_read_profile": "m1-dev-operator",
            "owner_identity_arn": "management",
            "target_read_identity_arn": "target",
        }
        declaration = copy.deepcopy(self.baseline)
        declaration["assignments"] = [
            {"target_account_id": a, "principal_id": "user", "principal_type": "USER"}
            for a in maintenance.ACCOUNTS
        ]

        def replies(boundary=False):
            values = [
                {"Account": a, "Arn": "management" if a == "835990279085" else "target"}
                for a in maintenance.ACCOUNTS
            ]
            values += [
                {"InlinePolicy": json.dumps(declaration["inline_policy"])},
                {"AccountIds": maintenance.ACCOUNTS},
            ]
            for a in maintenance.ACCOUNTS:
                role = {
                    "Arn": f"arn:aws:iam::{a}:role/aws-reserved/sso.amazonaws.com/{maintenance.runtime.ROLES[a]}"
                }
                if boundary:
                    role["PermissionsBoundary"] = {"PermissionsBoundaryArn": "unexpected"}
                values += [
                    {"Role": role},
                    {"PolicyNames": ["AwsSSOInlinePolicy"]},
                    {"AttachedPolicies": []},
                    {"PolicyDocument": declaration["inline_policy"]},
                    {"AccountAssignments": [{"PrincipalId": "user", "PrincipalType": "USER"}]},
                ]
            return values

        with patch.object(maintenance.runtime, "aws", side_effect=replies()):
            maintenance.live({}, approval, declaration, self.root / "good-postflight.json")
        self.assertEqual(len(maintenance.load(self.root / "good-postflight.json")["calls"]), 14)
        with patch.object(maintenance.runtime, "aws", side_effect=replies(True)):
            with self.assertRaisesRegex(ValueError, "boundary"):
                maintenance.live({}, approval, declaration, self.root / "failed-postflight.json")

    def test_seal_approval_cannot_authorize_apply(self):
        approval = {
            "operation": "seal",
            "approved": True,
            "contract_sha256": maintenance.digest(self.path),
            "workflow_sha256": maintenance.workflow_hash(),
            "manifest_sha256": None,
            "reprovisioning_accounts": maintenance.ACCOUNTS,
            "reprovisioning_impact_acknowledged": True,
            "owner_profile": "identity-center-admin",
            "owner_identity_arn": "human-owner",
            "target_read_profile": "m1-dev-operator",
            "target_read_identity_arn": "human-target",
        }
        path = self.root / "approval.json"
        self.write(path, approval)
        maintenance.approved(path, "seal", self.path)
        with self.assertRaisesRegex(ValueError, "Separate exact human approval"):
            maintenance.approved(path, "apply", self.path)
        approval["workflow_sha256"] = "tampered"
        self.write(path, approval)
        with self.assertRaises(ValueError):
            maintenance.approved(path, "seal", self.path)
