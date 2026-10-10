"""Exact policy resource addition and bounded restricted-plan safety; no AWS calls."""

import copy
import importlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
p = importlib.import_module("plan_iot_config_read")


def actions(policy):
    return {
        a
        for s in policy["Statement"]
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }


class ExactReadProposalTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = p.declarations()
        self.env = {
            "AGENT_MODE": "1",
            "AWS_PROFILE": "identity-center-plan",
            "AWS_REGION": "us-east-1",
            "EXPECTED_AWS_ACCOUNT": "835990279085",
        }
        self.managed = {address: {"id": "synthetic-" + address} for address in p.EXPECTED}
        self.managed[p.POLICY] = {
            "id": "synthetic-policy",
            "permission_set_arn": p.PS_ARN,
            "instance_arn": p.INSTANCE,
            "inline_policy": json.dumps(self.old["inline_policy"]),
        }
        self.fixture = {"complete": True, "resource_changes": []}
        for address, attrs in self.managed.items():
            after = copy.deepcopy(attrs)
            if address == p.POLICY:
                after["inline_policy"] = json.dumps(self.new["inline_policy"])
            self.fixture["resource_changes"].append(
                {
                    "address": address,
                    "mode": "managed",
                    "type": address.split(".")[0],
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["update"] if address == p.POLICY else ["no-op"],
                        "before": copy.deepcopy(attrs),
                        "after": after,
                        "after_unknown": {},
                    },
                }
            )

    def test_action_set_conditions_identity_and_only_single_resource_are_preserved(self):
        self.assertEqual(actions(self.old["inline_policy"]), actions(self.new["inline_policy"]))
        self.assertEqual(len(actions(self.new["inline_policy"])), 32)
        old = copy.deepcopy(self.old)
        next(s for s in old["inline_policy"]["Statement"] if s["Sid"] == "ReadBindingAndRuntime")[
            "Resource"
        ].append(p.SSM_ARN)
        self.assertEqual(old, self.new)
        self.assertEqual(self.new["assignments"], self.old["assignments"])
        self.assertEqual(self.new["session_duration"], "PT1H")
        self.assertNotIn("*", p.SSM_ARN)
        self.assertTrue(p.SSM_ARN.startswith("arn:aws:ssm:us-east-1:623155450153:"))

    def test_any_other_scope_action_assignment_or_condition_change_is_rejected(self):
        for mutate in (
            lambda c: c["inline_policy"]["Statement"][1].update(Action="ssm:*"),
            lambda c: c["inline_policy"]["Statement"][1]["Resource"].append("*"),
            lambda c: c["inline_policy"]["Statement"][1]["Resource"].append(p.SSM_ARN),
            lambda c: c["inline_policy"]["Statement"][-1].pop("Condition"),
            lambda c: c["assignments"][0].update(principal_id="other"),
            lambda c: c.update(session_duration="PT2H"),
        ):
            changed = copy.deepcopy(self.new)
            mutate(changed)
            with patch.object(p, "load", return_value=changed), self.assertRaises(ValueError):
                p.declarations()

    def test_only_one_inplace_update_and_six_noops_pass(self):
        p.validate_plan(self.fixture, self.managed, self.old, self.new)
        for address in p.EXPECTED:
            for action in (["create"], ["delete"], ["delete", "create"], ["create", "delete"]):
                changed = copy.deepcopy(self.fixture)
                next(r for r in changed["resource_changes"] if r["address"] == address)["change"][
                    "actions"
                ] = action
                with self.subTest(address=address, action=action), self.assertRaises(ValueError):
                    p.validate_plan(changed, self.managed, self.old, self.new)
        for address in p.EXPECTED - {p.POLICY}:
            changed = copy.deepcopy(self.fixture)
            next(r for r in changed["resource_changes"] if r["address"] == address)["change"][
                "actions"
            ] = ["update"]
            with self.assertRaises(ValueError):
                p.validate_plan(changed, self.managed, self.old, self.new)

    def test_import_move_scope_expansion_unknowns_and_extra_resources_stop(self):
        mutations = (
            lambda f: f["resource_changes"].append(copy.deepcopy(f["resource_changes"][0])),
            lambda f: f["resource_changes"][0].update(previous_address="other"),
            lambda f: f["resource_changes"][0]["change"].update(importing={"id": "adopt"}),
            lambda f: f.update(resource_drift=[{}]),
            lambda f: next(r for r in f["resource_changes"] if r["address"] == p.POLICY)[
                "change"
            ].update(after_unknown={"inline_policy": True}),
            lambda f: next(r for r in f["resource_changes"] if r["address"] == p.POLICY)["change"][
                "after"
            ].update(inline_policy=json.dumps(self.old["inline_policy"])),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.fixture)
            mutate(changed)
            with self.assertRaises(ValueError):
                p.validate_plan(changed, self.managed, self.old, self.new)

    def test_modes_profiles_accounts_and_argument_overrides_fail_before_any_tools(self):
        for edit in (
            {"AGENT_MODE": "0", "AWS_MUTATION_APPROVED": "1"},
            {"AWS_PROFILE": "identity-center-admin"},
            {"AWS_PROFILE": "strall-dev-plan"},
            {"EXPECTED_AWS_ACCOUNT": "623155450153"},
            {"AWS_REGION": "us-west-2"},
            {"TF_CLI_ARGS_plan": "-target=other"},
            {"AWS_ACCESS_KEY_ID": "synthetic"},
            {"AWS_ENDPOINT_URL": "https://unexpected.invalid"},
        ):
            with (
                patch.object(p, "aws_read") as aws,
                patch.object(p, "runtime") as runtime,
                self.assertRaises(ValueError),
            ):
                p.plan(self.env | edit)
            aws.assert_not_called()
            runtime.assert_not_called()

    def test_wrong_caller_identity_stops_before_owner_or_ssodata(self):
        for caller in (
            {"Account": "623155450153", "Arn": "other"},
            {
                "Account": "835990279085",
                "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_AdministratorAccess_abcdef/human",
            },
        ):
            with (
                patch.object(p, "aws_read", return_value=caller) as aws,
                patch.object(p, "runtime") as runtime,
                self.assertRaises(ValueError),
            ):
                p.plan(self.env)
            self.assertEqual(aws.call_count, 1)
            runtime.assert_not_called()

    def test_direct_aws_writer_is_rejected_and_cli_is_plan_only(self):
        with patch.object(p.subprocess, "run") as run, self.assertRaises(ValueError):
            p.aws_read(self.env, "ssm", "put-parameter")
        run.assert_not_called()
        for action in ("seal", "apply", "destroy"):
            with (
                patch.object(sys, "argv", ["bounded-plan", action]),
                patch("sys.stderr"),
                self.assertRaises(SystemExit),
            ):
                p.main()

    def run_synthetic_plan(self, *, fail=False):
        with tempfile.TemporaryDirectory() as scratch:
            owner = Path(scratch)
            previous = owner / "maintenance-reviews" / p.PUB_REVIEW
            previous.mkdir(parents=True)
            (previous / p.OVERLAY).write_text("synthetic reviewed additive source")
            (previous / p.RECEIPT).parent.mkdir(parents=True)
            (previous / p.RECEIPT).write_text("synthetic verified historical receipt")
            (owner / ".terraform").mkdir()
            (owner / "main.tf").write_text("synthetic original source")
            (owner / ".terraform.lock.hcl").write_text("synthetic lock")
            (owner / ".terraform/terraform.tfstate").write_text("synthetic local backend")
            (owner / "bootstrap.tfvars.json").write_text(
                json.dumps({"bootstrap_config_json": "historical"})
            )
            resources = []
            for address, attrs in self.managed.items():
                base, _, index = address.partition("[")
                kind, name = base.split(".")
                instance = {"attributes": attrs}
                if index:
                    instance["index_key"] = json.loads(index[:-1])
                resources.append(
                    {"mode": "managed", "type": kind, "name": name, "instances": [instance]}
                )
            state = {"lineage": p.LINEAGE, "serial": 13, "resources": resources}
            (owner / "terraform.tfstate").write_text(json.dumps(state))
            original = {path: path.read_bytes() for path in owner.rglob("*") if path.is_file()}
            calls = []
            rendered = copy.deepcopy(self.fixture)
            rendered["variables"] = {"bootstrap_config_json": {"value": json.dumps(self.new)}}

            def managed(snapshot):
                result = {}
                for resource in snapshot["resources"]:
                    for instance in resource["instances"]:
                        address = resource["type"] + "." + resource["name"]
                        if "index_key" in instance:
                            address += "[" + json.dumps(instance["index_key"]) + "]"
                        result[address] = instance["attributes"]
                return result

            def run(command, **kwargs):
                calls.append(command)
                self.assertEqual(kwargs["cwd"], owner)
                self.assertTrue((owner / p.OVERLAY).exists())
                if command[1] == "plan":
                    self.assertIn("-lock=false", command)
                    if fail:
                        return subprocess.CompletedProcess(command, 1)
                    binary = Path(next(c[5:] for c in command if c.startswith("-out=")))
                    with zipfile.ZipFile(binary, "w") as archive:
                        for source in owner.glob("*.tf"):
                            archive.write(source, "tfconfig/m-/" + source.name)
                        archive.write(owner / ".terraform.lock.hcl", ".terraform.lock.hcl")
                        archive.writestr("tfstate-prev", json.dumps(state))
                elif command[1] == "show":
                    kwargs["stdout"].write(json.dumps(rendered))
                else:
                    self.fail("No apply/init/state command permitted")
                return subprocess.CompletedProcess(command, 0)

            def hashes(base, names):
                return {name: p.sha(base / name) for name in names}

            execution = SimpleNamespace(
                owner_files=lambda _: {
                    "terraform.tfstate",
                    "main.tf",
                    "bootstrap.tfvars.json",
                    ".terraform.lock.hcl",
                    ".terraform/terraform.tfstate",
                },
                safe_hashes=hashes,
                owner_workflow=SimpleNamespace(managed_state=managed),
                publisher=SimpleNamespace(generate=lambda *args: None),
            )
            with (
                patch.object(p, "OWNER", owner),
                patch.object(p, "runtime", return_value=(execution, None)),
                patch.object(p, "validate_owner", return_value=(state, self.managed, previous)),
                patch.object(p, "live_checks") as live,
                patch.object(
                    p,
                    "aws_read",
                    return_value={
                        "Account": "835990279085",
                        "Arn": "arn:aws:sts::835990279085:assumed-role/AWSReservedSSO_IaCPlanReadOnly_abcdef/user",
                    },
                ) as aws,
                patch.object(p.subprocess, "run", side_effect=run),
                patch("builtins.print"),
            ):
                if fail:
                    with self.assertRaises(ValueError):
                        p.plan(self.env)
                else:
                    out = p.plan(self.env)
                    record = p.load(out / "owner.json")
                    self.assertEqual(
                        (record["creates"], record["changes"], record["deletes"]), (0, 1, 0)
                    )
                    self.assertEqual(record["owner_directory"], str(owner))
                    self.assertFalse(record["apply_supported"])
                    self.assertFalse((out / "terraform.tfstate").exists())
                live.assert_called_once()
                aws.assert_called_once()
            self.assertEqual([c[1] for c in calls], ["plan"] if fail else ["plan", "show"])
            self.assertFalse((owner / p.OVERLAY).exists())
            for path, content in original.items():
                self.assertEqual(path.read_bytes(), content)

    def test_plan_uses_same_owner_and_only_additive_snapshot_without_init_or_apply(self):
        self.run_synthetic_plan()

    def test_failed_plan_removes_only_overlay_and_never_repairs_or_retries_state(self):
        self.run_synthetic_plan(fail=True)


if __name__ == "__main__":
    unittest.main()
