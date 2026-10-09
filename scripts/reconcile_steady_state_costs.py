#!/usr/bin/env python3

import argparse
import calendar
import datetime as dt
import json
import pathlib
import subprocess
import sys
from decimal import Decimal, InvalidOperation


def fail(message):
    print(f"❌ {message}", file=sys.stderr)
    sys.exit(1)


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        fail(f"Invalid monetary value: {value!r}")


def previous_month_window(today=None):
    today = today or dt.date.today()
    first_this_month = today.replace(day=1)
    last_prev_month = first_this_month - dt.timedelta(days=1)
    start = last_prev_month.replace(day=1)
    return start.isoformat(), first_this_month.isoformat()


def run_aws(profile, args):
    cmd = ["aws", *args, "--profile", profile, "--output", "json", "--no-cli-pager"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"AWS CLI failed for profile {profile}: {' '.join(cmd)}\n{result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"AWS CLI returned invalid JSON for profile {profile}: {exc}")


def parse_profiles(values):
    mappings = {}
    for value in values:
        if "=" not in value:
            fail(f"Profile mapping must be target=profile, got: {value}")
        target, profile = value.split("=", 1)
        target = target.strip()
        profile = profile.strip()
        if not target or not profile:
            fail(f"Profile mapping must be target=profile, got: {value}")
        if target in mappings:
            fail(f"Duplicate profile mapping for target: {target}")
        mappings[target] = profile
    return mappings


def load_contract(path):
    try:
        contract = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"Contract not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"Invalid contract JSON: {exc}")

    if contract.get("schema_version") != 1:
        fail("Unsupported or missing schema_version")
    if contract.get("currency") != "USD":
        fail("Only USD contracts are supported")
    criteria = contract.get("acceptance_criteria", {})
    if criteria.get("remediation_mode") != "proposal_only":
        fail("Contract must require remediation_mode=proposal_only")
    if criteria.get("allow_destructive_actions") is not False:
        fail("Contract must explicitly disable destructive actions")
    return contract


def cost_by_service(profile, start, end):
    payload = run_aws(
        profile,
        [
            "ce",
            "get-cost-and-usage",
            "--region",
            "us-east-1",
            "--time-period",
            f"Start={start},End={end}",
            "--granularity",
            "MONTHLY",
            "--metrics",
            "UnblendedCost",
            "--group-by",
            "Type=DIMENSION,Key=SERVICE",
        ],
    )

    results = payload.get("ResultsByTime", [])
    if len(results) != 1:
        fail(f"Expected one monthly Cost Explorer result for {profile}, got {len(results)}")

    services = []
    actual = Decimal("0")
    for group in results[0].get("Groups", []):
        service = group.get("Keys", ["UNKNOWN"])[0]
        amount = money(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", "0"))
        actual += amount
        if amount != 0:
            services.append({"service": service, "cost_usd": format(amount, "f")})

    services.sort(key=lambda item: money(item["cost_usd"]), reverse=True)
    return actual, services


def identity(profile):
    payload = run_aws(profile, ["sts", "get-caller-identity"])
    return {
        "account_id": payload.get("Account"),
        "arn": payload.get("Arn"),
    }


def reconcile_target(target, profile, start, end):
    expected = money(target["monthly_target_usd"])
    actual, services = cost_by_service(profile, start, end)
    ident = identity(profile)

    expected_cents = expected.quantize(Decimal("0.01"))
    actual_cents = actual.quantize(Decimal("0.01"))
    variance = actual - expected

    return {
        "id": target["id"],
        "account_environment": target["account_environment"],
        "profile": profile,
        "account_id": ident["account_id"],
        "caller_arn": ident["arn"],
        "period": {"start": start, "end": end},
        "target_usd": format(expected, "f"),
        "actual_usd": format(actual, "f"),
        "variance_usd": format(variance, "f"),
        "status": "PASS" if actual_cents == expected_cents else "FAIL",
        "service_costs": services,
    }


def main():
    default_start, default_end = previous_month_window()

    parser = argparse.ArgumentParser(
        description="Read-only AWS steady-state cost reconciliation. No apply/delete operations exist in this tool."
    )
    parser.add_argument("--contract", required=True, type=pathlib.Path)
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        metavar="TARGET=AWS_PROFILE",
        help="Map each contract target id to an AWS CLI profile; repeat once per target",
    )
    parser.add_argument("--start", default=default_start, help="Inclusive YYYY-MM-DD (default: first day of previous month)")
    parser.add_argument("--end", default=default_end, help="Exclusive YYYY-MM-DD (default: first day of current month)")
    parser.add_argument("--output", type=pathlib.Path, help="Optional JSON evidence output path")
    args = parser.parse_args()

    contract = load_contract(args.contract)
    profiles = parse_profiles(args.profile)
    targets = contract.get("targets", [])

    target_ids = {target.get("id") for target in targets}
    if set(profiles) != target_ids:
        missing = sorted(target_ids - set(profiles))
        extra = sorted(set(profiles) - target_ids)
        fail(f"Profile mappings must match contract targets exactly. missing={missing}, extra={extra}")

    reconciled = [
        reconcile_target(target, profiles[target["id"]], args.start, args.end)
        for target in targets
    ]

    combined_target = money(contract["combined_monthly_target_usd"])
    combined_actual = sum((money(item["actual_usd"]) for item in reconciled), Decimal("0"))
    combined_status = "PASS" if all(item["status"] == "PASS" for item in reconciled) else "FAIL"

    evidence = {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_contract": str(args.contract),
        "read_only": True,
        "destructive_actions_available": False,
        "period": {"start": args.start, "end": args.end},
        "targets": reconciled,
        "combined": {
            "target_usd": format(combined_target, "f"),
            "actual_usd": format(combined_actual, "f"),
            "variance_usd": format(combined_actual - combined_target, "f"),
            "status": combined_status,
        },
        "limitations": [
            "This slice reconciles account-level Cost Explorer spend to the declared target.",
            "Service grouping accounts for observed account spend but does not yet prove desired-resource vs actual-resource inventory.",
            "No remediation is executed; any follow-up changes require a separate reviewed path.",
        ],
    }

    rendered = json.dumps(evidence, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
        print(f"\n✅ Evidence written to {args.output}", file=sys.stderr)

    if combined_status != "PASS":
        sys.exit(2)


if __name__ == "__main__":
    main()
