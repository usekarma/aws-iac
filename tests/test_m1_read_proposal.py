"""Offline safety regression for the proposed IAM discovery delta."""

import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "proposals/m1-read-discovery"
POLICY = json.loads((ROOT / "discovery-policy.json").read_text())
REFERENCE = json.loads((ROOT / "authorization-reference.json").read_text())


def validate(policy):
    """Validate proposal constraints, not effective AWS authorization."""
    for statement in policy["Statement"]:
        assert statement["Effect"] == "Allow"
        guards = statement["Condition"]["StringEquals"]
        assert guards["aws:PrincipalAccount"] == "623155450153"
        for action in statement["Action"]:
            service, name = action.split(":")
            metadata = REFERENCE[service]["actions"][name]
            properties = metadata["Annotations"]["Properties"]
            assert not properties["IsWrite"]
            assert not properties["IsPermissionManagement"]
            assert not properties["IsTaggingOnly"]
            if service != "iam":
                assert guards["aws:RequestedRegion"] == "us-east-1"
            if statement["Resource"] == "*":
                assert not metadata.get("Resources")


class ReadProposalTests(unittest.TestCase):
    def test_read_only_supported_actions_and_guards(self):
        validate(POLICY)

    def test_no_active_terraform_or_mutation_actions(self):
        actions = {a for s in POLICY["Statement"] for a in s["Action"]}
        self.assertFalse(actions & {"iam:PassRole", "sts:AssumeRole", "iot:Publish"})
        self.assertNotIn("*", actions)
        self.assertEqual(len(POLICY["Statement"]), 9)

    def test_widened_principal_is_rejected(self):
        policy = copy.deepcopy(POLICY)
        policy["Statement"][0]["Condition"]["StringEquals"]["aws:PrincipalAccount"] = "*"
        with self.assertRaises(AssertionError):
            validate(policy)

    def test_unsupported_action_is_rejected(self):
        policy = copy.deepcopy(POLICY)
        policy["Statement"][0]["Action"].append("iot:Publish")
        with self.assertRaises(KeyError):
            validate(policy)

    def test_scoped_action_cannot_be_widened_to_star(self):
        policy = copy.deepcopy(POLICY)
        policy["Statement"][1]["Resource"] = "*"
        with self.assertRaises(AssertionError):
            validate(policy)

    def test_only_exact_state_prefixes(self):
        statement = next(s for s in POLICY["Statement"] if s["Sid"] == "StateVersionOwnership")
        self.assertEqual(
            statement["Condition"]["StringEquals"]["s3:prefix"],
            [
                "iot-digital-twin/operational-demo/terraform.tfstate",
                "iot-digital-twin/atom-lite-001/terraform.tfstate",
            ],
        )
        self.assertEqual(statement["Resource"], "arn:aws:s3:::623155450153-tf-state")
