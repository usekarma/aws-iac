import copy
import unittest

import review_m1_staged_plan as gate


class StagePlanTests(unittest.TestCase):
    def plan(self, stage):
        rows = []
        for address in sorted(
            gate.ROLE
            | {"terraform_data.mode"}
            | (gate.OPERATIONAL if stage == "operational" else set())
        ):
            actions = ["create"] if stage == "service-role-bootstrap" else ["no-op"]
            rows.append(
                {"address": address, "change": {"actions": actions, "before": {}, "after": {}}}
            )
        return {"complete": True, "resource_changes": rows}

    def test_bootstrap_only(self):
        gate.review(self.plan("service-role-bootstrap"), "service-role-bootstrap")

    def test_operational_retains_role(self):
        gate.review(self.plan("operational"), "operational")

    def test_bootstrap_operational_deletion_rejected(self):
        plan = self.plan("service-role-bootstrap")
        plan["resource_changes"].append(
            {
                "address": "module.operational[0].awscc_iotsitewise_asset.asset",
                "change": {"actions": ["delete"]},
            }
        )
        with self.assertRaises(ValueError):
            gate.review(plan, "service-role-bootstrap")

    def test_stage_two_role_replacement_rejected(self):
        plan = self.plan("operational")
        plan["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        with self.assertRaises(ValueError):
            gate.review(plan, "operational")

    def test_missing_state_role_rejected(self):
        plan = copy.deepcopy(self.plan("operational"))
        plan["resource_changes"].pop(0)
        with self.assertRaises(ValueError):
            gate.review(plan, "operational")

    def test_extra_role_in_operational_module_rejected(self):
        plan = self.plan("operational")
        plan["resource_changes"].append(
            {
                "address": "module.operational[0].aws_iam_role.unreviewed",
                "change": {"actions": ["create"]},
            }
        )
        with self.assertRaises(ValueError):
            gate.review(plan, "operational")
