import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "inventory_report", ROOT / "scripts/inventory_report.py"
)
inventory_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory_report)


class InventoryTests(unittest.TestCase):
    def test_detached_storage_and_eip_surface_without_delete_authority(self):
        value = {
            "volumes": [
                {"Id": "vol-abc", "State": "available", "Attachments": []},
                {"Id": "vol-def", "State": "in-use", "Attachments": [{}]},
            ],
            "addresses": [{"Id": "eipalloc-abc", "Association": None}],
            "snapshots": [{"Id": "snap-abc", "State": "completed"}],
            "images": [],
            "load-balancers": [],
            "nat-gateways": [],
        }
        report = inventory_report.classify(value)
        self.assertEqual(len(report["candidates"]), 3)
        self.assertEqual(report["authority"], "inspection-only-no-deletion-approval")
        self.assertNotIn("vol-def", str(report))
