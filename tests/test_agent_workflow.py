import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agent_workflow", ROOT / "scripts/agent_workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def request():
    value = json.loads((ROOT / "examples/agent-workflow-iot.json").read_text())
    value["builder"] = {"complete": True, "summary": "Synthetic repository implementation complete"}
    value["allowed_paths"] = ["components/iot-digital-twin/"]
    for role in workflow.REVIEWS:
        value["reviews"][role] = {
            "summary": "Synthetic assessment",
            "findings": [],
            "blocking_findings": [],
        }
    return value


def snapshot():
    return {
        "iac_commit": "fixture-iac",
        "verification_base": "fixture-base",
        "desired_state_commit": "fixture-config",
        "desired_state_files": {},
        "config_contract_sha256": "fixture-hash",
        "files_changed": {"components/iot-digital-twin/main.tf": "fixture-content"},
    }


def checks():
    return [
        {
            "name": name,
            "command": command,
            "status": "PASS",
            "returncode": 0,
            "evidence_kind": "local_static",
            "log": name + ".log",
        }
        for name, command in workflow.gate_commands(request(), Path("/fixture-config"))
    ]


class WorkflowTests(unittest.TestCase):
    def test_existing_verification_owns_tests_and_module_validation(self):
        commands = workflow.gate_commands(request(), Path("/config"))
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            commands[1][1], ["bash", "scripts/verify.sh", "--terraform", "iot-digital-twin"]
        )
        self.assertFalse(
            any(
                command in (["make", "test"], ["bash", "scripts/verify.sh"])
                for _, command in commands
            )
        )

    def test_evaluation_skips_builder_scope_and_remediation(self):
        value = request()
        value["builder"] = None
        value["allowed_paths"] = []
        before = snapshot()
        before["files_changed"]["unrelated-local-work.md"] = "preserved"
        report = workflow.assemble(value, before, before, checks(), 0, evaluation=True)
        self.assertEqual(report["mode"], "EVALUATION_ONLY")
        self.assertEqual(report["final_state"], "READY_FOR_HUMAN_REVIEW")
        self.assertIsNone(report["builder_report"])
        self.assertNotIn("builder", [x["stage"] for x in report["transitions"]])
        self.assertEqual(report["remediation_remaining"], 0)
        self.assertEqual(report["stop"], "STOP_FOR_HUMAN")
        with patch.object(workflow, "run_gates") as gates:
            with self.assertRaisesRegex(ValueError, "cannot remediate"):
                workflow.execute(value, remediate=True, evaluation=True)
            gates.assert_not_called()

    def test_evaluation_without_source_does_not_invent_one(self):
        value = workflow.evaluation_request("iot-digital-twin")
        self.assertIsNone(workflow.validate(value, evaluation=True))
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(
                workflow.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ),
        ):
            gates = workflow.run_gates(value, None, Path(temporary))
        compatibility = next(x for x in gates if x["name"] == "config_compatibility")
        self.assertEqual(compatibility["status"], "NOT_AVAILABLE")
        self.assertIsNone(compatibility["command"])
        report = workflow.assemble(value, snapshot(), snapshot(), gates, 0, evaluation=True)
        self.assertEqual(report["final_state"], "BLOCKED")
        self.assertEqual(report["remediation_remaining"], 0)
        self.assertTrue(any("alignment" in x for x in report["unresolved_blockers"]))

    def test_evaluation_markdown_contains_human_review_sections(self):
        value = request()
        value["builder"] = None
        value["allowed_paths"] = []
        report = workflow.assemble(value, snapshot(), snapshot(), checks(), 0, evaluation=True)
        with tempfile.TemporaryDirectory() as temporary:
            workflow.write_evidence(Path(temporary), value, report)
            markdown = (Path(temporary) / "report.md").read_text()
        for text in [
            "iot-digital-twin",
            "Desired-state source",
            "Checks run",
            "Security findings",
            "Operations, cost and persistence findings",
            "Destructive/replacement",
            "Unresolved blockers",
            "Required human decisions",
            "READY_FOR_HUMAN_REVIEW",
            "NOT_INVOKED",
            "STOP_FOR_HUMAN",
        ]:
            self.assertIn(text, markdown)

    def test_ready_stops_with_no_plan_or_live_evidence(self):
        report = workflow.assemble(request(), snapshot(), snapshot(), checks(), 0)
        self.assertEqual(report["final_state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(report["stop"], "STOP_FOR_HUMAN")
        self.assertEqual(
            [x["stage"] for x in report["transitions"]], list(workflow.ROLES) + ["STOP_FOR_HUMAN"]
        )
        self.assertEqual(report["plan_evidence"]["status"], "NOT_PRODUCED")
        self.assertEqual(report["live_aws_evidence"]["status"], "NOT_COLLECTED")

    def test_failed_checks_missing_reviews_and_scope_block(self):
        value = request()
        value["reviews"]["security"]["summary"] = ""
        value["reviews"]["operations"]["blocking_findings"] = ["Recovery unknown"]
        before = snapshot()
        before["files_changed"]["scripts/deploy.sh"] = "outside-scope"
        gates = checks()
        gates[0]["status"] = "FAIL"
        report = workflow.assemble(value, before, before, gates, 0)
        self.assertEqual(report["final_state"], "BLOCKED")
        self.assertEqual(report["remediation_remaining"], 1)
        self.assertGreaterEqual(len(report["unresolved_blockers"]), 4)
        self.assertEqual(report["stop"], "STOP_FOR_HUMAN")

    def test_missing_checks_and_changed_snapshot_block(self):
        after = snapshot()
        after["iac_commit"] = "different"
        report = workflow.assemble(request(), snapshot(), after, [], 1)
        self.assertEqual(report["final_state"], "BLOCKED")
        self.assertEqual(report["remediation_remaining"], 0)
        self.assertEqual(report["transitions"][0]["stage"], "ONE_REMEDIATION_PASS")

    def test_fixed_gates_and_credentials_isolated_even_with_approval_flags(self):
        with patch.dict(
            os.environ,
            {
                "AWS_PROFILE": "production",
                "AWS_ACCESS_KEY_ID": "credential",
                "AWS_MUTATION_APPROVED": "1",
                "AGENT_MODE": "0",
                "TF_CLI_ARGS": "apply",
                "TG_BACKEND_BOOTSTRAP": "1",
            },
        ):
            env = workflow.isolated_environment(Path("/private-home"), Path("/config"))
        self.assertEqual(env["AGENT_MODE"], "1")
        for key in [
            "AWS_PROFILE",
            "AWS_ACCESS_KEY_ID",
            "AWS_MUTATION_APPROVED",
            "TF_CLI_ARGS",
            "TG_BACKEND_BOOTSTRAP",
        ]:
            self.assertNotIn(key, env)
        for _, command in workflow.gate_commands(request(), Path("/config")):
            self.assertNotIn("aws", command)
            self.assertNotIn("apply", command)
            self.assertNotIn("destroy", command)
            self.assertNotIn("--auto-approve", command)
            self.assertFalse(any("deploy.sh" in x or "plan.sh" in x for x in command))

    def test_request_command_hooks_rejected_before_execution(self):
        value = request()
        value["commands"] = ["terraform apply"]
        with self.assertRaises(ValueError):
            workflow.validate(value)

    def test_gate_errors_are_not_success(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(
                workflow.subprocess, "run", side_effect=subprocess.TimeoutExpired("gate", 1)
            ),
        ):
            gates = workflow.run_gates(request(), Path("/config"), Path(temporary))
        self.assertTrue(all(g["status"] == "ERROR" for g in gates))
        self.assertEqual(
            workflow.assemble(request(), snapshot(), snapshot(), gates, 0)["final_state"], "BLOCKED"
        )

    def test_only_one_remediation_and_prior_evidence_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifacts/agent-workflow/test"
            source = root / "request.json"
            value = request()
            value["builder"]["complete"] = False
            source.write_text(json.dumps(value))
            state = snapshot()
            state["desired_state_files"] = {
                name: "fixture-hash" for name in value["desired_state"]["config_paths"]
            }
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "validate", return_value=root),
                patch.object(workflow, "snapshot", return_value=state),
                patch.object(workflow, "run_gates", return_value=checks()),
                patch.object(workflow, "digest", return_value="fixture-hash"),
                patch.object(workflow, "git", return_value="fixture-config"),
            ):
                first = workflow.execute(source, output)
                self.assertEqual(first["final_state"], "BLOCKED")
                initial = (output / "cycle-0/evidence.json").read_bytes()
                value["builder"]["complete"] = True
                source.write_text(json.dumps(value))
                ready = workflow.execute(source, output, remediate=True)
                self.assertEqual(ready["final_state"], "READY_FOR_HUMAN_REVIEW")
                self.assertEqual((output / "cycle-0/evidence.json").read_bytes(), initial)
                with self.assertRaises(FileExistsError):
                    workflow.execute(source, output, remediate=True)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "cycle-1/evidence.json").stat().st_mode & 0o777, 0o600)

    def test_deterministic_summary_and_ready_run_cannot_remediate(self):
        self.assertEqual(
            workflow.assemble(request(), snapshot(), snapshot(), checks(), 0),
            workflow.assemble(request(), snapshot(), snapshot(), checks(), 0),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifacts/agent-workflow/test"
            source = root / "request.json"
            source.write_text(json.dumps(request()))
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "validate", return_value=root),
                patch.object(workflow, "snapshot", return_value=snapshot()),
                patch.object(workflow, "run_gates", return_value=checks()),
            ):
                workflow.execute(source, output)
                with self.assertRaises(ValueError):
                    workflow.execute(source, output, remediate=True)

    def test_changed_remediation_scope_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "request.json"
            output = root / "artifacts/agent-workflow/test"
            value = request()
            value["builder"]["complete"] = False
            source.write_text(json.dumps(value))
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "validate", return_value=root),
                patch.object(workflow, "snapshot", return_value=snapshot()),
                patch.object(workflow, "run_gates", return_value=checks()) as gates,
            ):
                workflow.execute(source, output)
                changed = copy.deepcopy(value)
                changed["allowed_paths"].append("scripts/")
                source.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "same blocked work request"):
                    workflow.execute(source, output, remediate=True)
                self.assertEqual(gates.call_count, 1)

    def test_tampered_previous_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "request.json"
            output = root / "artifacts/agent-workflow/test"
            value = request()
            value["builder"]["complete"] = False
            source.write_text(json.dumps(value))
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "validate", return_value=root),
                patch.object(workflow, "snapshot", return_value=snapshot()),
                patch.object(workflow, "run_gates", return_value=checks()) as gates,
            ):
                workflow.execute(source, output)
                (output / "cycle-0/report.md").write_text("altered report")
                with self.assertRaisesRegex(ValueError, "integrity"):
                    workflow.execute(source, output, remediate=True)
                self.assertEqual(gates.call_count, 1)


if __name__ == "__main__":
    unittest.main()
