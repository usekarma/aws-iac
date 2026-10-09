"""Reviewed bootstrap declaration and policy boundaries; no AWS access."""

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/identity-center-owner.iac-plan-readonly.json"
COMPONENT = ROOT / "components/identity-center-permission-set"


class IdentityCenterDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(EXAMPLE.read_text())

    def test_exact_reviewed_identity_and_assignment(self):
        self.assertEqual(self.config["administration_account_id"], "835990279085")
        self.assertEqual(self.config["permission_set_name"], "IaCPlanReadOnly")
        self.assertEqual(self.config["session_duration"], "PT1H")
        self.assertEqual(
            self.config["instance_arn"], "arn:aws:sso:::instance/ssoins-7223e8cbef5c5b91"
        )
        self.assertEqual(
            self.config["assignments"],
            [
                {
                    "target_account_id": "623155450153",
                    "principal_type": "USER",
                    "principal_id": "b4486448-d011-7037-9cfb-c16c43f591e1",
                }
            ],
        )

    def test_inline_policy_exactly_matches_human_reviewed_document(self):
        policy = self.config["inline_policy"]
        canonical = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "43f0d7d3f42e95037872b8e90ec11228f2ab869382fdc13c27b493b3e5423d0e",
        )

    def test_policy_has_only_expected_read_actions_and_no_mutation_wildcards(self):
        expected = {
            "sts:GetCallerIdentity",
            "ssm:DescribeParameters",
            "ssm:GetParameter",
            "ssm:ListTagsForResource",
            "dynamodb:DescribeTable",
            "dynamodb:GetItem",
            "s3:ListBucket",
            "s3:GetBucketVersioning",
            "s3:GetObject",
            "s3:GetBucketLocation",
            "s3:GetBucketTagging",
            "s3:GetBucketAcl",
            "s3:GetBucketCors",
            "s3:GetBucketWebsite",
            "s3:GetBucketLogging",
            "s3:GetBucketRequestPayment",
            "s3:GetAccelerateConfiguration",
            "s3:GetBucketPolicy",
            "s3:GetBucketObjectLockConfiguration",
            "s3:GetReplicationConfiguration",
            "s3:GetLifecycleConfiguration",
            "s3:GetEncryptionConfiguration",
            "s3:GetBucketPublicAccessBlock",
            "s3:GetBucketOwnershipControls",
        }
        actual = set()
        for statement in self.config["inline_policy"]["Statement"]:
            self.assertEqual(statement["Effect"], "Allow")
            actions = statement["Action"]
            for action in [actions] if isinstance(actions, str) else actions:
                self.assertRegex(action, r"^[a-z0-9]+:(Get|List|Describe)[A-Za-z]+$")
                self.assertNotIn("*", action)
                actual.add(action)
        self.assertEqual(actual, expected)

    def test_component_manages_only_identity_center_resources(self):
        terraform = "\n".join(p.read_text() for p in COMPONENT.glob("*.tf"))
        self.assertEqual(
            set(re.findall(r'resource "([^"]+)"', terraform)),
            {
                "aws_ssoadmin_permission_set",
                "aws_ssoadmin_permission_set_inline_policy",
                "aws_ssoadmin_account_assignment",
            },
        )
        self.assertIn("allowed_account_ids = [var.administration_account_id]", terraform)
        self.assertIn(
            "depends_on = [aws_ssoadmin_permission_set_inline_policy.inline_policy]", terraform
        )
        self.assertNotIn("IaCPlanReadOnly", terraform)
        for prohibited in (
            "AdministratorAccess",
            "PowerUserAccess",
            "ReadOnlyAccess",
            "kms:Decrypt",
        ):
            self.assertNotIn(prohibited, terraform)
