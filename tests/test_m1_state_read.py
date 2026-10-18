"""Canonical state access preserves the existing owner and exact scope."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StateReadProposalTests(unittest.TestCase):
    def test_exact_object_read_preserves_policy_and_assignments(self):
        base = json.loads(
            (
                ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-provider-read.json"
            ).read_text()
        )
        candidate = json.loads(
            (
                ROOT / "examples/identity-center-owner.iac-plan-readonly.m1-state-read.json"
            ).read_text()
        )
        addition = candidate["inline_policy"]["Statement"].pop()
        self.assertEqual(candidate, base)
        self.assertEqual(len(base["inline_policy"]["Statement"]), 19)
        self.assertEqual(
            addition,
            {
                "Sid": "M1CanonicalOperationalStateRead",
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::623155450153-tf-state/iot-digital-twin/operational-demo/terraform.tfstate",
                "Condition": {
                    "StringEquals": {
                        "aws:PrincipalAccount": "623155450153",
                        "s3:ResourceAccount": "623155450153",
                    }
                },
            },
        )
