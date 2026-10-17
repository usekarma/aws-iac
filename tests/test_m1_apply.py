"""Mocked human workflow tests: no AWS, Terraform mutation or real bundle writes."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import apply_m1_discovery as workflow
import test_m1_discovery_plan as plan_fixtures


class ApplyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.review = Path(self.temp.name)
        self.approval_path = self.review / "approval.json"
        self.approved = {
            "operation": "m1-discovery-exact-apply",
            "approved": True,
            "plan_sha256": workflow.seal.PLAN_HASH,
            "manifest_sha256": workflow.MANIFEST_HASH,
            "reprovisioning_accounts": workflow.seal.ACCOUNTS,
            "owner_profile": "identity-center-admin",
            "owner_identity_arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_44494c40ddbff199/test",
            "target_read_profile": "operator-target-reader",
            "target_read_identity_arn": "arn:aws:sts::623155450153:assumed-role/AuthorizedReader/test",
            "workflow_sha256": workflow.seal.digest(Path(workflow.__file__)),
        }
        self.approval_path.write_text(json.dumps(self.approved))

    def mocks(self):
        patches = {
            "environment": patch.object(workflow, "environment", return_value={}),
            "guard": patch.object(workflow, "guard_identity", return_value={}),
            "manifest": patch.object(workflow, "manifest", return_value={}),
            "validate": patch.object(workflow.seal, "validate", return_value={}),
            "before": patch.object(workflow, "live_before"),
            "postflight": patch.object(workflow, "postflight", return_value={"status": "verified"}),
            "run": patch.object(workflow.subprocess, "run"),
        }
        active = {}
        for name, item in patches.items():
            active[name] = item.start()
            self.addCleanup(item.stop)
        active["run"].return_value.returncode = 0
        return active

    def test_approval_binds_both_hashes_and_workflow(self):
        self.assertEqual(workflow.approval(self.approval_path), self.approved)
        self.approved["workflow_sha256"] = "tampered"
        self.approval_path.write_text(json.dumps(self.approved))
        with self.assertRaises(ValueError):
            workflow.approval(self.approval_path)

    def test_second_account_ack_required(self):
        self.approved["reprovisioning_accounts"] = ["623155450153"]
        self.approval_path.write_text(json.dumps(self.approved))
        with self.assertRaises(ValueError):
            workflow.approval(self.approval_path)

    def test_agent_cannot_apply(self):
        with patch.dict(
            workflow.os.environ, {"AGENT_MODE": "1", "HUMAN_M1_APPLY_APPROVED": "1"}, clear=True
        ):
            with self.assertRaises(ValueError):
                workflow.environment()

    def test_competing_credentials_rejected(self):
        with patch.dict(
            workflow.os.environ,
            {"AGENT_MODE": "0", "HUMAN_M1_APPLY_APPROVED": "1", "AWS_ROLE_ARN": "override"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                workflow.environment()

    def test_exact_saved_plan_only_and_no_second_attempt(self):
        mocked = self.mocks()
        workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        args = mocked["run"].call_args.args[0]
        self.assertEqual(
            args,
            ["terraform", "apply", "-input=false", "-no-color", str(self.review / "review.tfplan")],
        )
        with self.assertRaises(FileExistsError):
            workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        self.assertEqual(mocked["run"].call_count, 1)

    def test_terraform_failure_has_receipt_no_retry_or_postflight(self):
        mocked = self.mocks()
        mocked["run"].return_value.returncode = 1
        with self.assertRaises(ValueError):
            workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        self.assertEqual(mocked["run"].call_count, 1)
        mocked["postflight"].assert_not_called()
        receipt = json.loads((self.review / "m1-apply-receipt.json").read_text())
        self.assertEqual(receipt["status"], "failed-stop-for-human")
        self.assertEqual(receipt["terraform_exit_code"], 1)

    def test_postflight_failure_records_successful_apply_and_stops(self):
        mocked = self.mocks()
        mocked["postflight"].side_effect = ValueError("partial provisioning")
        with self.assertRaises(ValueError):
            workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        receipt = json.loads((self.review / "m1-apply-receipt.json").read_text())
        self.assertEqual(receipt["terraform_exit_code"], 0)
        self.assertEqual(receipt["status"], "failed-stop-for-human")
        self.assertEqual(mocked["run"].call_count, 1)

    def test_manifest_failure_prevents_apply(self):
        mocked = self.mocks()
        mocked["manifest"].side_effect = ValueError("tampered")
        with self.assertRaises(ValueError):
            workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        mocked["run"].assert_not_called()

    def test_live_drift_prevents_apply(self):
        mocked = self.mocks()
        mocked["before"].side_effect = ValueError("live drift")
        with self.assertRaises(ValueError):
            workflow.execute("apply", workflow.seal.OWNER, self.review, self.approval_path)
        mocked["run"].assert_not_called()

    def test_wrong_identity_rejected(self):
        with patch.object(
            workflow, "aws", return_value={"Account": "623155450153", "Arn": "wrong"}
        ):
            with self.assertRaises(ValueError):
                workflow.guard_identity({}, "existing-profile", "expected", "835990279085")

    def test_missing_second_account_provisioning_fails(self):
        _, new = workflow.seal.contract.declarations()
        with patch.object(
            workflow,
            "aws",
            side_effect=[
                {"InlinePolicy": json.dumps(new["inline_policy"])},
                {"AccountIds": ["623155450153"]},
            ],
        ):
            with self.assertRaises(ValueError):
                workflow.verify_live({}, self.approved)

    def test_manifest_tampering_rejected_without_mocking_validator(self):
        (self.review / "m1-maintenance-manifest.json").write_text("tampered")
        with self.assertRaises(ValueError):
            workflow.manifest(workflow.seal.OWNER, self.review)

    def test_post_apply_state_only_exact_after_attributes(self):
        plan, state = plan_fixtures.M1PlanTests().fixture()
        state.update(serial=16, lineage="adda9261-8df8-2be4-51cf-f829529878b3")
        for resource in state["resources"]:
            for instance in resource["instances"]:
                if (
                    resource["type"] == "aws_ssoadmin_permission_set_inline_policy"
                    and resource["name"] == "inline_policy"
                ):
                    row = next(
                        r
                        for r in plan["resource_changes"]
                        if r["address"] == workflow.seal.contract.owner.POLICY
                    )
                    instance["attributes"] = row["change"]["after"]
        owner = self.review / "owner"
        owner.mkdir()
        (owner / "terraform.tfstate").write_text(json.dumps(state))
        (self.review / "plan.json").write_text(json.dumps(plan))
        workflow.state_after(owner, self.review)
        state["resources"][0]["instances"][0]["attributes"]["unexpected"] = "change"
        (owner / "terraform.tfstate").write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            workflow.state_after(owner, self.review)

    def test_two_account_postflight_policy_delivery(self):
        _, new = workflow.seal.contract.declarations()
        calls = []

        def read(env, profile, *args):
            calls.append((profile, args))
            service, operation = args[:2]
            if operation == "get-inline-policy-for-permission-set":
                return {"InlinePolicy": json.dumps(new["inline_policy"])}
            if operation == "list-accounts-for-provisioned-permission-set":
                return {"AccountIds": workflow.seal.ACCOUNTS}
            if operation == "get-caller-identity":
                owner = profile == self.approved["owner_profile"]
                return {
                    "Account": "835990279085" if owner else "623155450153",
                    "Arn": self.approved["owner_identity_arn"]
                    if owner
                    else self.approved["target_read_identity_arn"],
                }
            if operation == "get-role":
                return {"Role": {}}
            if operation == "list-role-policies":
                return {"PolicyNames": ["inline"]}
            if operation == "list-attached-role-policies":
                return {"AttachedPolicies": []}
            if operation == "get-role-policy":
                return {"PolicyDocument": new["inline_policy"]}
            if operation == "list-account-assignments":
                account = args[-1]
                return {
                    "AccountAssignments": [
                        {"PrincipalType": a["principal_type"], "PrincipalId": a["principal_id"]}
                        for a in new["assignments"]
                        if a["target_account_id"] == account
                    ]
                }
            raise AssertionError((service, operation))

        with patch.object(workflow, "aws", side_effect=read):
            workflow.verify_live({}, self.approved)
        profiles = {profile for profile, args in calls if args[1] == "get-role-policy"}
        self.assertEqual(
            profiles, {self.approved["owner_profile"], self.approved["target_read_profile"]}
        )
