"""Review behavior is tested with synthetic plans and private temporary outputs."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evidence", ROOT / "scripts/evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class EvidenceTests(unittest.TestCase):
    def test_delete_and_replacement_require_data_review_without_values(self):
        plan = json.loads((ROOT / "examples/teardown.synthetic.json").read_text())
        rows = evidence.analyze(plan)
        self.assertIn("potential-irreversible-data-loss", rows[0]["flags"])
        self.assertNotIn("NEVER_INCLUDE_PLAN_VALUES", json.dumps(rows))
        plan["resource_changes"][0]["change"]["actions"] = ["create", "delete"]
        self.assertIn("potential-irreversible-data-loss", evidence.analyze(plan)[0]["flags"])

    def test_unknown_action_and_incomplete_plan_fail(self):
        for value in (
            {"format_version": "1.2", "resource_changes": [], "complete": False},
            {"format_version": "2.0", "resource_changes": []},
            {},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evidence.analyze(value)
        value = {
            "format_version": "1.2",
            "resource_changes": [
                {"type": "aws_instance", "address": "x", "change": {"actions": ["execute"]}}
            ],
        }
        with self.assertRaises(ValueError):
            evidence.analyze(value)

    def test_private_artifacts_and_no_approval_or_values(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "private"
            result = evidence.generate(
                ROOT / "examples/teardown.synthetic.json",
                ROOT / "examples/review-context.synthetic.json",
                out,
            )
            self.assertEqual(result["required_approval"], "strong-destructive")
            self.assertTrue(result["source"]["synthetic"])
            self.assertFalse(result["source"]["binding_verified_by_generator"])
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            self.assertEqual((out / "evidence.json").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("NEVER_INCLUDE_PLAN_VALUES", (out / "evidence.json").read_text())
            with self.assertRaises(ValueError):
                evidence.generate(
                    ROOT / "examples/teardown.synthetic.json",
                    ROOT / "examples/review-context.synthetic.json",
                    out,
                )

    def test_forget_survival_and_iam_network_flags(self):
        resources = []
        for kind, action in [
            ("aws_ebs_volume", "forget"),
            ("aws_iam_role", "update"),
            ("aws_security_group", "create"),
        ]:
            resources.append(
                {"type": kind, "address": kind + ".x", "change": {"actions": [action]}}
            )
        rows = evidence.analyze({"format_version": "1.2", "resource_changes": resources})
        self.assertIn("state-forget-resource-may-survive-and-cost-money", rows[0]["flags"])
        self.assertIn("security-boundary-approval", rows[1]["flags"])
        self.assertIn("network-boundary-approval", rows[2]["flags"])
