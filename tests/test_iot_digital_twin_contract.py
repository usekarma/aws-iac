import json
import unittest
from pathlib import Path


class IotDigitalTwinConfigContractTests(unittest.TestCase):
    def test_iot_digital_twin_config_carries_contract_fields(self):
        config_path = (
            Path(__file__).resolve().parent.parent
            / "aws-config"
            / "iac"
            / "dev"
            / "iot-digital-twin"
            / "core2-aws-001"
            / "config.json"
        )
        self.assertTrue(config_path.exists(), "Expected aws-config contract file to exist")

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


if __name__ == "__main__":
    unittest.main()
