import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONFIG_RELATIVE_PATH = Path("iac/dev/iot-digital-twin/atom-lite-001/config.json")


def contract_path():
    checkout = os.environ.get("AWS_CONFIG_DIR", "aws-config")
    if not checkout.strip():
        raise ValueError("AWS_CONFIG_DIR must name an explicit checkout")
    return (ROOT / checkout).resolve() / CONFIG_RELATIVE_PATH


class IotDigitalTwinConfigContractTests(unittest.TestCase):
    def test_iot_digital_twin_config_carries_contract_fields(self):
        config_path = contract_path()
        self.assertTrue(
            config_path.is_file(),
            f"Expected aws-config contract file at {config_path}; "
            "set AWS_CONFIG_DIR to the explicit local checkout (CI uses aws-config/)",
        )

        config = json.loads(config_path.read_text())
        from scripts.check_lambda_declarations import validate_config

        validate_config(config, "iot-digital-twin")
        self.assertEqual(config["project"], "iot-digital-twin")
        self.assertEqual(config["experiment"], "atom-lite-simulator")
        self.assertEqual(config["tags"]["Environment"], "sandbox")
        self.assertEqual(
            set(config["planning_dependencies"]),
            {"artifact_publication", "trusted_principal", "active_session", "sandbox_binding"},
        )
        for field in ("artifact", "expected_principal", "active_session", "region"):
            with self.subTest(field=field):
                self.assertIsNone(config[field])
        with self.assertRaisesRegex(ValueError, "Unresolved simulator bindings"):
            validate_config(config, "iot-digital-twin", require_resolved=True)


class ConfigCheckoutPathTests(unittest.TestCase):
    def test_ci_default_remains_nested_checkout(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(contract_path(), ROOT / "aws-config" / CONFIG_RELATIVE_PATH)

    def test_explicit_relative_checkout_is_repository_relative(self):
        with patch.dict(os.environ, {"AWS_CONFIG_DIR": "../aws-config"}):
            self.assertEqual(contract_path(), ROOT.parent / "aws-config" / CONFIG_RELATIVE_PATH)

    def test_explicit_absolute_checkout(self):
        with patch.dict(os.environ, {"AWS_CONFIG_DIR": "/explicit/config-checkout"}):
            self.assertEqual(
                contract_path(), Path("/explicit/config-checkout") / CONFIG_RELATIVE_PATH
            )

    def test_missing_explicit_checkout_does_not_fall_back(self):
        with patch.dict(os.environ, {"AWS_CONFIG_DIR": "missing-checkout"}):
            self.assertEqual(contract_path(), ROOT / "missing-checkout" / CONFIG_RELATIVE_PATH)
            with self.assertRaisesRegex(AssertionError, "set AWS_CONFIG_DIR"):
                IotDigitalTwinConfigContractTests(
                    "test_iot_digital_twin_config_carries_contract_fields"
                ).test_iot_digital_twin_config_carries_contract_fields()

    def test_empty_explicit_checkout_is_rejected(self):
        with patch.dict(os.environ, {"AWS_CONFIG_DIR": ""}):
            with self.assertRaisesRegex(ValueError, "explicit checkout"):
                contract_path()


if __name__ == "__main__":
    unittest.main()
