"""Synthetic recovery inputs; no real seal, apply, or AWS calls."""

import json
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

import m1_provider_recovery as recovery
import test_m1_provider_sealing as fixtures

VALIDATE_RECOVERY = recovery.require_recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.ProviderSealingTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f = f
        self.owner, self.review = f.owner, f.review
        f.state["serial"] = 18
        f.write(f.owner / "terraform.tfstate", f.state)
        pre = json.loads((f.review / "preflight.json").read_text())
        pre["serial"] = 18
        pre["owner_hashes"][str(f.owner / "terraform.tfstate")] = recovery.digest(
            f.owner / "terraform.tfstate"
        )
        f.write(f.review / "preflight.json", pre)
        plan_file = f.review / "review.tfplan"
        with zipfile.ZipFile(plan_file) as z:
            contents = {n: z.read(n) for n in z.namelist()}
        contents["tfstate"] = json.dumps(f.state).encode()
        with zipfile.ZipFile(plan_file, "w") as z:
            for n, value in contents.items():
                z.writestr(n, value)
        self.binding = {
            "schema_version": 1,
            "owner_directory": str(f.owner),
            "review_directory": str(f.review),
            "serial": 18,
            "lineage": recovery.LINEAGE,
            "state_sha256": recovery.digest(f.owner / "terraform.tfstate"),
            "source_commit": recovery.original.COMMIT,
            "review_hashes": {n: recovery.digest(f.review / n) for n in recovery.original.PINS},
            "recovery_hashes": {},
            "raw_directory": str(f.review / "raw"),
            "prior_review": str(f.review / "prior"),
            "prior_manifest_name": "m1-provider-read-manifest.json",
        }
        self.binding_file = f.owner / "binding.json"
        f.write(self.binding_file, self.binding)
        self.approval = f.owner / "recovery-approval.json"
        self.value = {
            "schema_version": 1,
            "operation": "m1-provider-read-recovery-seal-only",
            "plan_sha256": self.binding["review_hashes"]["review.tfplan"],
            "state_sha256": self.binding["state_sha256"],
            "binding_sha256": recovery.digest(self.binding_file),
            "workflow_sha256": recovery.digest(Path(recovery.__file__)),
            "eventual_reprovisioning_accounts": recovery.ACCOUNTS,
            "reprovisioning_impact_acknowledged": True,
            "seal_only_approved": True,
            "apply_approved": False,
        }
        f.write(self.approval, self.value)
        # Original plan hash differs from new synthetic recovery binary.
        patches = [
            patch.object(recovery, "OWNER", f.owner),
            patch.object(recovery.original, "REVIEW", f.owner / "old-review"),
            patch.object(recovery, "require_recovery"),
            patch.object(recovery, "rendered_plan", return_value=f.plan),
            patch.dict(recovery.original.PINS, {"review.tfplan": "old-plan"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def verify(self):
        return recovery.validate(self.owner, self.review, self.approval, self.binding_file)

    def test_new_binding_keeps_delta_and_approval_separate(self):
        self.assertFalse(self.verify()["apply_authorized"])

    def test_binding_tampering_invalidates_approval(self):
        self.binding["source_commit"] = "different"
        self.f.write(self.binding_file, self.binding)
        with self.assertRaises(ValueError):
            self.verify()

    def test_stale_state_rejected(self):
        self.f.state["serial"] = 19
        self.f.write(self.owner / "terraform.tfstate", self.f.state)
        with self.assertRaises(ValueError):
            self.verify()

    def test_old_plan_not_reusable(self):
        with patch.dict(recovery.original.PINS, self.binding["review_hashes"]):
            with self.assertRaises(ValueError):
                self.verify()

    def test_recovery_hash_missing_or_changed(self):
        self.binding["recovery_hashes"] = {str(self.owner / "missing"): "hash"}
        self.f.write(self.binding_file, self.binding)
        with self.assertRaises(ValueError):
            self.verify()

    def test_unexpected_delta_rejected(self):
        row = next(
            r
            for r in self.f.plan["resource_changes"]
            if r["address"] == recovery.owner_contract.POLICY
        )
        policy = json.loads(row["change"]["after"]["inline_policy"])
        policy["Statement"][-1]["Action"].append("iam:PassRole")
        row["change"]["after"]["inline_policy"] = json.dumps(policy)
        self.f.write(self.review / "plan.json", self.f.plan)
        self.binding["review_hashes"]["plan.json"] = recovery.digest(self.review / "plan.json")
        self.f.write(self.binding_file, self.binding)
        self.value["binding_sha256"] = recovery.digest(self.binding_file)
        self.f.write(self.approval, self.value)
        with self.assertRaises(ValueError):
            self.verify()

    def test_no_seal_overwrite(self):
        recovery.seal(self.owner, self.review, self.approval, self.binding_file)
        with self.assertRaises(ValueError):
            recovery.seal(self.owner, self.review, self.approval, self.binding_file)

    def test_missing_both_account_acknowledgment(self):
        self.value["reprovisioning_impact_acknowledged"] = False
        self.f.write(self.approval, self.value)
        with self.assertRaises(ValueError):
            self.verify()

    def test_recovery_apply_one_attempt_and_partial_failure(self):
        approval = self.owner / "apply-approval.json"
        value = {
            "operation": "m1-provider-read-recovery-apply",
            "approved": True,
            "workflow_sha256": recovery.digest(Path(recovery.__file__)),
            "plan_sha256": self.binding["review_hashes"]["review.tfplan"],
            "manifest_sha256": "synthetic-manifest",
            "binding_sha256": recovery.digest(self.binding_file),
            "reprovisioning_accounts": recovery.ACCOUNTS,
            "reprovisioning_impact_acknowledged": True,
            "owner_profile": "identity-center-admin",
            "owner_identity_arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_44494c40ddbff199/test",
            "target_read_profile": "human-target",
            "target_read_identity_arn": "human-target-arn",
        }
        self.f.write(approval, value)
        with (
            patch.object(recovery.execution, "environment", return_value={}),
            patch.object(recovery.execution, "guard_identity"),
            patch.object(recovery.execution, "verify_live"),
            patch.object(recovery, "validate"),
            patch.object(
                recovery, "execution_manifest", return_value={"approval_file": str(self.approval)}
            ),
            patch.object(recovery.execution.subprocess, "run") as run,
        ):
            run.return_value.returncode = 1
            with self.assertRaises(ValueError):
                recovery.execute("apply", self.owner, self.review, approval, self.binding_file)
            with self.assertRaises(FileExistsError):
                recovery.execute("apply", self.owner, self.review, approval, self.binding_file)
            self.assertEqual(run.call_count, 1)
            receipt = json.loads((self.review / "m1-provider-read-apply-receipt.json").read_text())
            self.assertEqual(receipt["terraform_exit_code"], 1)
            self.assertEqual(receipt["status"], "failed-stop-for-human")
            value["approved"] = False
            self.f.write(approval, value)
            with self.assertRaises(ValueError):
                recovery.execute("apply", self.owner, self.review, approval, self.binding_file)
            self.assertEqual(run.call_count, 1)

    def test_raw_reconciliation_complete_and_bad_policy_rejected(self):
        raw = Path(self.binding["raw_directory"])
        raw.mkdir()
        prior = Path(self.binding["prior_review"])
        prior.mkdir()
        old, _ = recovery.declarations()
        self.f.write(
            raw / "central-inline.json", {"InlinePolicy": json.dumps(old["inline_policy"])}
        )
        self.f.write(raw / "provisioned.json", {"AccountIds": recovery.ACCOUNTS})
        for filename, account in [
            ("owner-sts.json", "835990279085"),
            ("target-sts.json", "623155450153"),
        ]:
            self.f.write(
                raw / filename,
                {
                    "Account": account,
                    "Arn": "arn:aws:sts::" + account + ":assumed-role/Synthetic/test",
                },
            )
        for account in recovery.ACCOUNTS:
            role = recovery.execution.ROLES[account]
            values = {
                "role": {
                    "Role": {
                        "Arn": "arn:aws:iam::"
                        + account
                        + ":role/aws-reserved/sso.amazonaws.com/"
                        + role
                    }
                },
                "inline-names": {"PolicyNames": ["AwsSSOInlinePolicy"]},
                "managed": {"AttachedPolicies": []},
                "inline": {
                    "RoleName": role,
                    "PolicyName": "AwsSSOInlinePolicy",
                    "PolicyDocument": old["inline_policy"],
                },
                "assignments": {
                    "AccountAssignments": [
                        {
                            "AccountId": account,
                            "PermissionSetArn": recovery.execution.PS,
                            "PrincipalType": "USER",
                            "PrincipalId": recovery.owner_contract.PRINCIPAL,
                        }
                    ]
                },
            }
            for suffix, value in values.items():
                self.f.write(raw / (account + "-" + suffix + ".json"), value)
        (prior / "review.tfplan").write_bytes(b"old failed binary")
        self.f.write(prior / "plan.json", self.f.plan)
        self.f.write(
            prior / "m1-provider-read-manifest.json",
            {
                "owner_directory": str(self.owner),
                "review_directory": str(prior),
                "plan_sha256": recovery.digest(prior / "review.tfplan"),
                "review_files": {"plan.json": recovery.digest(prior / "plan.json")},
            },
        )
        self.f.write(
            prior / "m1-provider-read-apply-receipt.json",
            {
                "status": "failed-stop-for-human",
                "terraform_exit_code": 1,
                "manifest_sha256": recovery.digest(prior / "m1-provider-read-manifest.json"),
                "plan_sha256": recovery.digest(prior / "review.tfplan"),
            },
        )

        def bind():
            self.f.write(
                raw / "capture-hashes.json",
                {
                    f.name: recovery.digest(f)
                    for f in raw.glob("*.json")
                    if f.name != "capture-hashes.json"
                },
            )
            self.binding["recovery_hashes"] = {
                str(f): recovery.digest(f) for f in list(raw.glob("*.json")) + list(prior.glob("*"))
            }

        bind()
        VALIDATE_RECOVERY(self.binding)
        self.f.write(
            raw / "623155450153-inline.json",
            {
                "RoleName": recovery.execution.ROLES["623155450153"],
                "PolicyName": "AwsSSOInlinePolicy",
                "PolicyDocument": {"Statement": []},
            },
        )
        bind()
        with self.assertRaises(ValueError):
            VALIDATE_RECOVERY(self.binding)
