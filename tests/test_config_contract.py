import json
import tempfile
import unittest
from pathlib import Path

from check_config_contract import check_compatibility


class ConfigContractCompatibilityTests(unittest.TestCase):
    def write_contract(self, version):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "contracts").mkdir()
        (root / "contracts" / "config-contract.json").write_text(
            json.dumps({"contract_name": "aws-config", "contract_version": version})
        )
        return temp, root

    def test_supported_contract_version_passes(self):
        temp, root = self.write_contract(1)
        self.addCleanup(temp.cleanup)
        self.assertEqual(check_compatibility(root), 1)

    def test_unsupported_contract_version_fails(self):
        temp, root = self.write_contract(2)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ValueError, "Unsupported aws-config contract version 2"):
            check_compatibility(root)

    def test_missing_contract_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Missing contract file"):
                check_compatibility(Path(temp))


if __name__ == "__main__":
    unittest.main()
