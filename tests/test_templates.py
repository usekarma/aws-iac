"""Render a real template with synthetic values, without providers/backends/AWS."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TemplateTests(unittest.TestCase):
    def test_grafana_runtime_shell_interpolation_and_syntax(self):
        values = dict(
            GRAFANA_PORT=3000,
            CONNECT_PORT=8083,
            CH_HTTP_URL="http://synthetic:8123",
            CH_NAME="synthetic",
            MSK_BOOTSTRAP="",
            CONNECT_GROUP_ID="synthetic",
            MONGO_URI="",
            CONNECTOR_NAME="synthetic",
            CONNECTOR_JSON="{}",
        )
        template = ROOT / "components/grafana/userdata.sh.tmpl"
        expression = (
            "jsonencode(templatefile("
            + json.dumps(str(template))
            + ",jsondecode("
            + json.dumps(json.dumps(values))
            + ")))\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("TF_", "AWS_"))
            }
            env["TF_DATA_DIR"] = temp + "/.terraform"
            result = subprocess.run(
                ["terraform", "console", "-no-color"],
                input=expression,
                cwd=temp,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = json.loads(json.loads(result.stdout))
            self.assertIn("${KAFKA_VER}", rendered)
            self.assertIn("${DEB_VER}", rendered)
            self.assertIn("${mongo_connector_class:-", rendered)
            self.assertIn('GRAFANA_PORT="3000"', rendered)
            syntax = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
