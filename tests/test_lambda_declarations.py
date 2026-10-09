import copy
import json
import os
import unittest

import hcl2

from scripts.check_lambda_declarations import (
    DRAFT_SCHEMA,
    ROOT,
    SCHEMA,
    validate_config,
    validate_declaration,
)


def declaration():
    return json.loads((ROOT / "examples/lambda-declaration.synthetic.json").read_text())


class LambdaDeclarationTests(unittest.TestCase):
    def test_explicit_declaration_and_generic_metadata(self):
        value = declaration()
        value.update(src_type="clickhouse", src_nickname="synthetic", vpc_nickname="synthetic")
        validate_config({"functions": {"synthetic-service": value}}, "lambda")

    def test_empty_or_missing_function_map_fails_closed(self):
        for value in ({}, {"functions": {}}):
            with self.assertRaises(ValueError):
                validate_config(value, "lambda")

    def test_missing_artifact_and_legacy_placeholder_fail(self):
        for artifact in (None, {}, {**declaration()["artifact"], "s3_key": "v1/empty.zip"}):
            value = declaration()
            if artifact is None:
                del value["artifact"]
            else:
                value["artifact"] = artifact
            with self.assertRaises(ValueError):
                validate_declaration(value)

    def test_unversioned_or_invalid_digest_fails(self):
        for field, value in [
            ("s3_object_version", ""),
            ("s3_object_version", "null"),
            ("s3_object_version", "latest"),
            ("s3_object_version", " "),
            ("source_code_hash", "not-a-digest"),
        ]:
            item = declaration()
            item["artifact"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_declaration(item)

    def test_iam_and_cloud_authority_fields_are_rejected(self):
        for field in ("iam_policy", "role_arn", "account", "profile", "command", "apply"):
            value = declaration()
            value[field] = "forbidden"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_declaration(value)

    def test_invalid_sizing_and_retention_fail(self):
        for field, value in [
            ("memory_size", 127),
            ("timeout", 901),
            ("timeout", 1.5),
            ("log_retention_days", 2),
        ]:
            item = declaration()
            item[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_declaration(item)

    def test_iot_requires_runtime_handler_identity_topic_and_retention(self):
        value = {
            "ingest_function": declaration(),
            "device_id": "synthetic-device",
            "mqtt_topic": "devices/synthetic-device/telemetry",
            "cloudwatch_log_retention_days": 14,
        }
        validate_config(value, "iot-digital-twin")
        for field, change in [
            ("runtime", "python3.11"),
            ("handler", "handler.lambda_handler"),
            ("environment", {}),
            ("log_retention_days", 30),
        ]:
            wrong = copy.deepcopy(value)
            wrong["ingest_function"][field] = change
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_config(wrong, "iot-digital-twin")
        value["mqtt_topic"] = "devices/another/telemetry"
        with self.assertRaises(ValueError):
            validate_config(value, "iot-digital-twin")

    def test_explicit_draft_is_structural_only_and_strict_readiness_fails(self):
        value = {
            "ingest_function": declaration(),
            "device_id": "synthetic-device",
            "mqtt_topic": "devices/synthetic-device/telemetry",
            "cloudwatch_log_retention_days": 14,
        }
        value["ingest_function"]["artifact"] = None
        value["ingest_function"]["environment"] = {}
        value["ingest_function"]["planning_dependencies"] = [
            "artifact_publication",
            "trusted_principal",
        ]
        validate_config(value, "iot-digital-twin")
        with self.assertRaises(ValueError):
            validate_config(value, "iot-digital-twin", require_resolved=True)
        for dependencies in ([], ["artifact_publication"], ["trusted_principal"], ["unknown"]):
            wrong = copy.deepcopy(value)
            wrong["ingest_function"]["planning_dependencies"] = dependencies
            with self.subTest(dependencies=dependencies), self.assertRaises(ValueError):
                validate_config(wrong, "iot-digital-twin")
        del value["ingest_function"]["artifact"]
        with self.assertRaises(ValueError):
            validate_config(value, "iot-digital-twin")

    def test_merged_config_schema_and_draft_are_compatible(self):
        checkout = (ROOT / os.environ.get("AWS_CONFIG_DIR", "aws-config")).resolve()
        schema = json.loads((checkout / "schemas/iot-digital-twin.schema.json").read_text())
        self.assertEqual(schema["properties"]["ingest_function"]["oneOf"], [SCHEMA, DRAFT_SCHEMA])
        config = json.loads(
            (checkout / "iac/dev/iot-digital-twin/core2-aws-001/config.json").read_text()
        )
        validate_config(config, "iot-digital-twin")

    def test_iot_trust_and_resource_address_moves_are_preserved(self):
        text = (ROOT / "components/iot-digital-twin/main.tf").read_text()
        parsed = hcl2.loads(text)
        resources = {kind: blocks for group in parsed["resource"] for kind, blocks in group.items()}
        rule = resources["aws_iot_topic_rule"]["telemetry"]
        self.assertIn("principal() AS principal, topic() AS topic", rule["sql"])
        permission = resources["aws_lambda_permission"]["iot_trigger"]
        self.assertEqual(permission["source_arn"], "${aws_iot_topic_rule.telemetry.arn}")
        self.assertEqual(
            permission["source_account"], "${data.aws_caller_identity.current.account_id}"
        )
        self.assertEqual(len(parsed["moved"]), 2)
        self.assertIn("EXPECTED_DEVICE_ID", text)
        self.assertIn("EXPECTED_PRINCIPAL", text)
        self.assertIn("LATEST_STATE_TABLE", text)
        self.assertNotIn("dynamodb:Query", text)
        self.assertNotIn("parameter${var.iac_prefix}/*", text)
        self.assertFalse((ROOT / "components/iot-digital-twin/empty.zip").exists())
        self.assertFalse((ROOT / "components/lambda/empty.zip").exists())

    def test_shared_module_has_no_out_of_band_code_or_runtime_ownership(self):
        for path in [ROOT / "modules/lambda/main.tf", ROOT / "components/lambda/main.tf"]:
            self.assertNotIn("ignore_changes", path.read_text())
        self.assertIn("//components/", (ROOT / "terragrunt.hcl").read_text())


if __name__ == "__main__":
    unittest.main()
