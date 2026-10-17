"""Synthetic plan safety tests, not live Terraform evidence."""

import copy
import json
import unittest

import review_m1_discovery_plan as proposal
import plan_iot_config_read as owner


class M1PlanTests(unittest.TestCase):
    def fixture(self):
        old, new = proposal.declarations()
        resources = []
        rows = []
        for address in sorted(owner.EXPECTED):
            base, *index = address.split("[", 1)
            kind, name = base.split(".")
            before = {"id": address}
            after = copy.deepcopy(before)
            actions = ["no-op"]
            if address == owner.POLICY:
                before["inline_policy"] = json.dumps(old["inline_policy"])
                after["inline_policy"] = json.dumps(new["inline_policy"])
                actions = ["update"]
            instance = {"attributes": before}
            if index:
                instance["index_key"] = json.loads(index[0][:-1])
            resources.append(
                {"mode": "managed", "type": kind, "name": name, "instances": [instance]}
            )
            rows.append(
                {
                    "address": address,
                    "type": kind,
                    "mode": "managed",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {"before": before, "after": after, "actions": actions},
                }
            )
        return {"complete": True, "resource_changes": rows}, {
            "version": 4,
            "lineage": "synthetic-owner",
            "resources": resources,
        }

    def test_single_additive_policy_update(self):
        proposal.review(*self.fixture())

    def test_assignment_change_rejected(self):
        plan, state = self.fixture()
        row = next(r for r in plan["resource_changes"] if r["address"] != owner.POLICY)
        row["change"]["actions"] = ["update"]
        with self.assertRaises(ValueError):
            proposal.review(plan, state)

    def test_policy_replacement_rejected(self):
        plan, state = self.fixture()
        row = next(r for r in plan["resource_changes"] if r["address"] == owner.POLICY)
        row["change"]["actions"] = ["delete", "create"]
        with self.assertRaises(ValueError):
            proposal.review(plan, state)

    def test_drift_rejected(self):
        plan, state = self.fixture()
        plan["resource_drift"] = [{"address": owner.POLICY}]
        with self.assertRaises(ValueError):
            proposal.review(plan, state)

    def test_extra_resource_rejected(self):
        plan, state = self.fixture()
        plan["resource_changes"].append(copy.deepcopy(plan["resource_changes"][0]))
        with self.assertRaises(ValueError):
            proposal.review(plan, state)
