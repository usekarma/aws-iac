"""Synthetic bundles only; never seal the real plan or invent operator approval."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import seal_m1_provider_reads as sealing
import test_m1_discovery_plan as fixtures


class ProviderSealingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = Path(self.temp.name) / "owner"
        self.review = Path(self.temp.name) / "review"
        self.owner.mkdir()
        self.review.mkdir()
        (self.owner / ".terraform").mkdir()
        old, new = sealing.declarations()
        with patch.object(fixtures.proposal, "declarations", return_value=(old, new)):
            self.plan, self.state = fixtures.M1PlanTests().fixture()
        self.state.update(serial=17, lineage=sealing.LINEAGE)
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
        for n in (
            "header.tf",
            "main.tf",
            "outputs.tf",
            "bootstrap_override.tf",
            ".terraform.lock.hcl",
        ):
            (self.owner / n).write_text("synthetic")
        self.write(self.owner / "bootstrap.tfvars.json", {"bootstrap_config_json": "synthetic"})
        variables = {"bootstrap_config_json": json.dumps(new)}
        self.write(self.review / "maintenance.tfvars.json", variables)
        self.plan["variables"] = {k: {"value": v} for k, v in variables.items()}
        self.write(self.review / "plan.json", self.plan)
        self.write(self.review / "rollback-declaration.json", old)
        (self.review / "terraform.log").write_text("synthetic")
        prior = self.owner / "maintenance-reviews/artifact-publisher-hrrbk83v"
        prior.mkdir(parents=True)
        (prior / sealing.OVERLAY).write_text("synthetic overlay")
        self.receipt = self.owner / "receipt.json"
        self.state_hash = sealing.digest(self.owner / "terraform.tfstate")
        self.write(
            self.receipt,
            {
                "status": "verified",
                "postflight": {
                    "status": "verified",
                    "serial": 17,
                    "lineage": sealing.LINEAGE,
                    "state_sha256": self.state_hash,
                    "reprovisioning_accounts": sealing.ACCOUNTS,
                },
            },
        )
        with zipfile.ZipFile(self.review / "review.tfplan", "w") as z:
            for f in self.owner.glob("*.tf"):
                z.writestr("tfconfig/m-/" + f.name, f.read_bytes())
            z.writestr("tfconfig/m-/" + sealing.OVERLAY, (prior / sealing.OVERLAY).read_bytes())
            z.writestr(".terraform.lock.hcl", (self.owner / ".terraform.lock.hcl").read_bytes())
            for n in ("tfstate", "tfstate-prev"):
                z.writestr(n, json.dumps(self.state))
        self.write(
            self.review / "preflight.json",
            {
                "serial": 17,
                "lineage": sealing.LINEAGE,
                "baseline_policy_statements": 18,
                "source_commit": sealing.COMMIT,
                "identity": {
                    "Account": "835990279085",
                    "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_3a3b95ed2606cc1b/synthetic",
                },
                "owner_hashes": {
                    str(self.owner / n): sealing.digest(self.owner / n) for n in sealing.OWNER_NAMES
                },
            },
        )
        self.write(self.review / "result.json", {"synthetic": True})
        self.pins = {n: sealing.digest(self.review / n) for n in sealing.PINS}
        self.approval = Path(self.temp.name) / "approval.json"
        self.write(
            self.approval,
            {
                "schema_version": 1,
                "operation": "m1-provider-read-seal-only",
                "plan_sha256": self.pins["review.tfplan"],
                "state_sha256": self.state_hash,
                "workflow_sha256": sealing.digest(Path(sealing.__file__)),
                "eventual_reprovisioning_accounts": sealing.ACCOUNTS,
                "reprovisioning_impact_acknowledged": True,
                "seal_only_approved": True,
                "apply_approved": False,
            },
        )
        for name, value in {
            "OWNER": self.owner,
            "REVIEW": self.review,
            "RECEIPT": self.receipt,
            "STATE_HASH": self.state_hash,
            "RECEIPT_HASH": sealing.digest(self.receipt),
            "PINS": self.pins,
        }.items():
            p = patch.object(sealing, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(sealing, "rendered_plan", return_value=copy.deepcopy(self.plan))
        p.start()
        self.addCleanup(p.stop)

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")

    def verify(self):
        return sealing.validate(self.owner, self.review, self.approval)

    def test_valid_seal_and_overwrite_rejected(self):
        self.assertFalse(self.verify()["apply_authorized"])
        sealing.seal(self.owner, self.review, self.approval)
        with self.assertRaises(ValueError):
            sealing.seal(self.owner, self.review, self.approval)

    def test_tampered_plan(self):
        (self.review / "review.tfplan").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.verify()

    def test_stale_state(self):
        self.state["serial"] = 18
        self.write(self.owner / "terraform.tfstate", self.state)
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_evidence(self):
        (self.review / "preflight.json").unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_rollback(self):
        (self.review / "rollback-declaration.json").unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_unexpected_permissions_and_assignment_rejected(self):
        for mutation in ("permissions", "assignment"):
            plan = copy.deepcopy(self.plan)
            row = next(
                r for r in plan["resource_changes"] if r["address"] == sealing.owner_contract.POLICY
            )
            if mutation == "permissions":
                policy = json.loads(row["change"]["after"]["inline_policy"])
                policy["Statement"][-1]["Action"].append("iam:PassRole")
                row["change"]["after"]["inline_policy"] = json.dumps(policy)
            else:
                row = next(
                    r
                    for r in plan["resource_changes"]
                    if r["address"] != sealing.owner_contract.POLICY
                )
                row["change"]["actions"] = ["update"]
            self.write(self.review / "plan.json", plan)
            with patch.dict(self.pins, {"plan.json": sealing.digest(self.review / "plan.json")}):
                with self.assertRaises(ValueError):
                    self.verify()

    def test_replacement_rejected(self):
        self.plan["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        self.write(self.review / "plan.json", self.plan)
        with patch.dict(self.pins, {"plan.json": sealing.digest(self.review / "plan.json")}):
            with self.assertRaises(ValueError):
                self.verify()

    def test_acknowledgment_and_apply_approval_rejected(self):
        value = json.loads(self.approval.read_text())
        for change in (
            {"reprovisioning_impact_acknowledged": False},
            {"apply_approved": True},
            {"eventual_reprovisioning_accounts": ["623155450153"]},
        ):
            self.write(self.approval, value | change)
            with self.assertRaises(ValueError):
                self.verify()

    def test_binary_json_mismatch(self):
        with patch.object(sealing, "rendered_plan", return_value={}):
            with self.assertRaises(ValueError):
                self.verify()
