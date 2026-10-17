"""Synthetic private-bundle regressions; never seals the real operator artifact."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import seal_m1_discovery as sealing
import test_m1_discovery_plan as plan_fixtures


class SealingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = Path(self.temp.name)
        self.review = self.owner / "maintenance-reviews/test"
        self.review.mkdir(parents=True)
        (self.owner / ".terraform").mkdir()
        self.prior = self.owner / sealing.PRIOR
        self.prior.mkdir(parents=True)
        self.plan, self.state = plan_fixtures.M1PlanTests().fixture()
        self.state.update(serial=15, lineage="adda9261-8df8-2be4-51cf-f829529878b3")
        self.old, new = sealing.contract.declarations()
        variables = {"bootstrap_config_json": "baseline"}
        self.write(self.owner / "bootstrap.tfvars.json", variables)
        variables["bootstrap_config_json"] = json.dumps(new)
        self.plan["variables"] = {k: {"value": v} for k, v in variables.items()}
        self.write(self.review / "maintenance.tfvars.json", variables)
        self.write(self.owner / "terraform.tfstate", self.state)
        self.write(
            self.owner / ".terraform/terraform.tfstate",
            {
                "backend": {
                    "type": "local",
                    "config": {"path": None, "workspace_dir": None},
                    "hash": 666019178,
                }
            },
        )
        for name in [
            "header.tf",
            "main.tf",
            "outputs.tf",
            "bootstrap_override.tf",
            ".terraform.lock.hcl",
        ]:
            (self.owner / name).write_text("synthetic source")
        (self.prior / sealing.OVERLAY).write_text("synthetic publisher")
        self.state_hash = sealing.digest(self.owner / "terraform.tfstate")
        self.write(
            self.prior / "post-apply.json", {"status": "verified", "state_sha256": self.state_hash}
        )
        self.write(self.review / "plan.json", self.plan)
        self.write(self.review / "rollback-declaration.json", self.old)
        (self.review / "terraform.log").write_text("synthetic plan log")
        with zipfile.ZipFile(self.review / "review.tfplan", "w") as archive:
            for path in self.owner.glob("*.tf"):
                archive.writestr("tfconfig/m-/" + path.name, path.read_bytes())
            archive.writestr(
                "tfconfig/m-/" + sealing.OVERLAY, (self.prior / sealing.OVERLAY).read_bytes()
            )
            archive.writestr(
                ".terraform.lock.hcl", (self.owner / ".terraform.lock.hcl").read_bytes()
            )
            archive.writestr("tfstate-prev", json.dumps(self.state))
        self.plan_hash = sealing.digest(self.review / "review.tfplan")
        self.evidence = {
            "status": "STOP_FOR_HUMAN",
            "sealed": False,
            "apply_authorized": False,
            "identity": {
                "Account": "835990279085",
                "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b/test",
            },
            "commit": "4954eed2eb6904260b08e8ecf73f5ec50ff5dc45",
            "plan_sha256": self.plan_hash,
            "reprovisioning_accounts": sealing.ACCOUNTS,
            "plan_json_sha256": sealing.digest(self.review / "plan.json"),
            "owner_hashes": {
                str(self.owner / name): sealing.digest(self.owner / name)
                for name in [
                    "header.tf",
                    "main.tf",
                    "outputs.tf",
                    "bootstrap_override.tf",
                    "terraform.tfstate",
                    ".terraform/terraform.tfstate",
                    ".terraform.lock.hcl",
                    "bootstrap.tfvars.json",
                ]
            },
        }
        self.write(self.review / "evidence.json", self.evidence)
        self.write(
            self.review / "owner.json",
            {
                "owner_directory": str(self.owner),
                "lineage": self.state["lineage"],
                "serial": 15,
                "state_sha256": self.state_hash,
                "verified_evidence_sha256": sealing.digest(self.review / "evidence.json"),
            },
        )
        self.context = {
            "schema_version": 1,
            "operation": "m1-discovery-seal-only",
            "owner_account": "835990279085",
            "grant_account": "623155450153",
            "region": "us-east-1",
            "plan_sha256": self.plan_hash,
            "eventual_reprovisioning_accounts": sealing.ACCOUNTS,
            "reprovisioning_impact_acknowledged": True,
            "seal_only_approved": True,
            "apply_approved": False,
        }
        self.write(self.review / "context.json", self.context)
        for name, value in [
            ("OWNER", self.owner),
            ("STATE_HASH", self.state_hash),
            ("PLAN_HASH", self.plan_hash),
        ]:
            patcher = patch.object(sealing, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(sealing, "rendered_plan", side_effect=lambda *_: self.plan)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def test_valid_seal_and_no_overwrite(self):
        before = (self.owner / "terraform.tfstate").read_bytes()
        sealing.seal(self.owner, self.review)
        manifest = self.review / "m1-maintenance-manifest.json"
        self.assertTrue(manifest.exists())
        self.assertFalse(json.loads(manifest.read_text())["apply_authorized"])
        self.assertEqual(before, (self.owner / "terraform.tfstate").read_bytes())
        with self.assertRaises(FileExistsError):
            sealing.seal(self.owner, self.review)

    def test_plan_tampering(self):
        (self.review / "review.tfplan").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_missing_context(self):
        (self.review / "context.json").unlink()
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_missing_owner_evidence(self):
        (self.review / "owner.json").unlink()
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_owner_tampering(self):
        (self.owner / "main.tf").write_text("tampered")
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_both_account_acknowledgment(self):
        self.context["eventual_reprovisioning_accounts"] = ["623155450153"]
        self.write(self.review / "context.json", self.context)
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_unexpected_change_rejected_even_with_matching_json_hash(self):
        self.plan["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        self.write(self.review / "plan.json", self.plan)
        self.evidence["plan_json_sha256"] = sealing.digest(self.review / "plan.json")
        self.write(self.review / "evidence.json", self.evidence)
        owner_record = json.loads((self.review / "owner.json").read_text())
        owner_record["verified_evidence_sha256"] = sealing.digest(self.review / "evidence.json")
        self.write(self.review / "owner.json", owner_record)
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_binary_json_mismatch(self):
        self.plan = copy.deepcopy(self.plan)
        self.plan["complete"] = False
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)

    def test_wrong_identity(self):
        self.evidence["identity"]["Account"] = "623155450153"
        self.write(self.review / "evidence.json", self.evidence)
        with self.assertRaises(ValueError):
            sealing.validate(self.owner, self.review)
