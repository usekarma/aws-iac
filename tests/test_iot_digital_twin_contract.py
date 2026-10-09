import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONFIG_RELATIVE_PATH = Path("iac/dev/iot-digital-twin/core2-aws-001/config.json")


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
        required = {
            "telemetry_rate_hz",
            "offline_timeout_seconds",
            "max_clock_skew_seconds",
            "max_retry_attempts",
            "least_privilege_iam",
            "no_broad_permission_fallback",
            "device_certificate_authoritative",
            "device_id_is_data_only",
            "reject_device_authored_offline",
            "connectivity_state_server_derived",
            "server_replay_and_stale_enforcement",
        }

        self.assertTrue(required.issubset(config.keys()))
        self.assertTrue(config["least_privilege_iam"])
        self.assertTrue(config["no_broad_permission_fallback"])
        self.assertTrue(config["device_certificate_authoritative"])
        self.assertTrue(config["reject_device_authored_offline"])


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
