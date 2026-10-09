#!/usr/bin/env python3
"""Offline synthetic demonstration; never contacts AWS or executes Terraform."""

from datetime import datetime, timezone
from pathlib import Path

from evidence import generate

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    output = ROOT / "artifacts" / ("demo-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    evidence = generate(
        ROOT / "examples/teardown.synthetic.json",
        ROOT / "examples/review-context.synthetic.json",
        output,
    )
    assert evidence["required_approval"] == "strong-destructive"
    print(
        f"Synthetic example written to {output}. STOP: no execution authority or live-state evidence."
    )
