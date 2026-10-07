import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("postflight", ROOT / "scripts/postflight.py")
postflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(postflight)


class PostflightTests(unittest.TestCase):
    def test_exact_volume_present_and_absent(self):
        with patch.object(
            postflight, "query", return_value={"Volumes": [{"VolumeId": "vol-abc"}]}
        ) as query:
            self.assertTrue(
                postflight.check({"type": "volume", "id": "vol-abc", "expected": "present"})
            )
            self.assertEqual(
                query.call_args.args[0],
                ["ec2", "describe-volumes", "--filters", "Name=volume-id,Values=vol-abc"],
            )
        with patch.object(postflight, "query", return_value={"Volumes": []}):
            self.assertTrue(
                postflight.check({"type": "volume", "id": "vol-abc", "expected": "absent"})
            )

    def test_permissions_error_never_counts_as_absent(self):
        with patch.object(postflight, "query", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                postflight.check({"type": "volume", "id": "vol-abc", "expected": "absent"})

    def test_arbitrary_command_and_bad_id_rejected(self):
        with patch.object(postflight, "query") as query:
            for kind, identifier in [("delete-volume", "vol-abc"), ("volume", "--all")]:
                with self.assertRaises(ValueError):
                    postflight.check({"type": kind, "id": identifier, "expected": "absent"})
            query.assert_not_called()
