"""Security scope regressions for an inactive service-role proposal."""

import json
from pathlib import Path
import re
import unittest

import hcl2

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/iot-operational-service-role/main.tf"


class ServiceRoleTests(unittest.TestCase):
    def test_resources_only_new_role_and_inline_policy(self):
        parsed = hcl2.loads(MODULE.read_text())
        kinds = [kind for block in parsed["resource"] for kind in block]
        self.assertEqual(kinds, ["aws_iam_role", "aws_iam_role_policy"])

    def test_no_runtime_or_credential_rights(self):
        actions = re.findall(r'"((?:iot|iotsitewise|iam|ssm|logs):[A-Za-z*]+)"', MODULE.read_text())
        self.assertTrue(actions)
        self.assertFalse(
            set(actions)
            & {
                "iot:Publish",
                "iot:Connect",
                "iot:CreateCertificateFromCsr",
                "iot:AttachPolicy",
                "ssm:PutParameter",
                "iotsitewise:BatchPutAssetPropertyValue",
                "iam:CreateRole",
                "iam:PutRolePolicy",
            }
        )
        self.assertFalse(any(action.endswith(":*") for action in actions))

    def test_not_wired_to_active_component(self):
        text = "\n".join(p.read_text() for p in (ROOT / "components/iot-digital-twin").glob("*.tf"))
        self.assertNotIn("iot-operational-service-role", text)

    def test_downstream_actions_are_declared_by_pinned_handlers(self):
        reference = json.loads((MODULE.parent / "handler-permissions.reference.json").read_text())
        required = {
            action
            for resource in reference["handlers"].values()
            for handler in resource.values()
            for action in handler["permissions"]
        }
        declared = {
            action
            for block in re.findall(r"Action\s*=\s*\[([^]]*)\]", MODULE.read_text())
            for action in re.findall(r'"((?:iot|iotsitewise|iam):[A-Za-z]+)"', block)
        }
        self.assertLessEqual(declared, required)
