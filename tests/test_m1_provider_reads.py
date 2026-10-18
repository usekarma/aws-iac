"""Scope and preservation tests for the proposed owner declaration."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProviderReadProposalTests(unittest.TestCase):
    def test_only_one_statement_added_and_owner_preserved(self):
        base = json.loads(
            (
                ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-discovery.json"
            ).read_text()
        )
        candidate = json.loads(
            (
                ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-provider-read.json"
            ).read_text()
        )
        delta = candidate["inline_policy"]["Statement"].pop()
        self.assertEqual(candidate, base)
        self.assertEqual(len(base["inline_policy"]["Statement"]), 18)
        self.assertEqual(
            delta,
            {
                "Sid": "M1CloudControlProviderReads",
                "Effect": "Allow",
                "Action": [
                    "iam:GetRole",
                    "iam:ListRolePolicies",
                    "iam:GetRolePolicy",
                    "iam:ListAttachedRolePolicies",
                ],
                "Resource": "arn:aws:iam::623155450153:role/iot-digital-twin-operational-m1-cloud-control",
                "Condition": {"StringEquals": {"aws:PrincipalAccount": "623155450153"}},
            },
        )
        self.assertEqual(
            {x["target_account_id"] for x in base["assignments"]},
            {"623155450153", "835990279085"},
        )
