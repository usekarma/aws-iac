import copy
import json
import os
import unittest

from scripts.check_lambda_declarations import ROOT, validate_config


class ActiveSimulatorContractTests(unittest.TestCase):
    def test_canonical_schema_and_readiness(self):
        checkout = (ROOT / os.environ.get("AWS_CONFIG_DIR", "aws-config")).resolve()
        config = json.loads(
            (checkout / "iac/dev/iot-digital-twin/atom-lite-001/config.json").read_text()
        )
        self.assertEqual(
            json.loads((ROOT / "contracts/iot-digital-twin.schema.json").read_text()),
            json.loads((checkout / "schemas/iot-digital-twin.schema.json").read_text()),
        )
        validate_config(config, "iot-digital-twin")
        with self.assertRaises(ValueError):
            validate_config(config, "iot-digital-twin", require_resolved=True)
        resolved = copy.deepcopy(config)
        resolved.pop("planning_dependencies")
        resolved.update(
            region="us-east-1",
            active_session="a" * 32,
            expected_principal="synthetic",
            artifact={
                "s3_bucket": "synthetic-bucket",
                "s3_key": "iot-digital-twin-simulator.zip",
                "s3_object_version": "synthetic",
                "source_code_hash": "A" * 43 + "=",
            },
        )
        validate_config(resolved, "iot-digital-twin", require_resolved=True)
        retired = json.loads((checkout / "archive/core2/core2-aws-001/config.json").read_text())
        with self.assertRaises(ValueError):
            validate_config(retired, "iot-digital-twin")
        self.assertFalse((ROOT / "components/iot-digital-twin-simulator").exists())
