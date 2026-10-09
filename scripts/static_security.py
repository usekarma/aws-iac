#!/usr/bin/env python3
"""Small IaC regression gate, not a comprehensive Terraform security audit."""

from collections import Counter
import json
from pathlib import Path
import re
import subprocess

import hcl2

RULES = {
    "force-destroy": r"\bforce_destroy\s*=\s*(?:true|try\([^\n]*,\s*true\))",
    "unencrypted-storage": r"\bencrypted\s*=\s*false",
    "skip-final-snapshot": r"\bskip_final_snapshot\s*=\s*true",
    "disable-prevent-destroy": r"\bprevent_destroy\s*=\s*false",
    "public-ip": r"\b(?:associate_public_ip_address|assign_public_ip)\s*=\s*true",
    "world-cidr": r'"(?:0\.0\.0\.0/0|::/0)"',
}


def findings(text):
    # Include comments conservatively; this gate reports risks for review, not exploitability.
    return Counter({name: len(re.findall(pattern, text)) for name, pattern in RULES.items()})


def check(base):
    additions = []
    total = Counter()
    paths = subprocess.check_output(["git", "ls-files", "--", "*.tf"], text=True).splitlines()
    paths += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "*.tf"], text=True
    ).splitlines()
    locals_by_module = {}
    references_by_module = {}
    for name in sorted(set(paths)):
        path = Path(name)
        if not path.exists():
            continue
        text = path.read_text()
        parsed = hcl2.loads(text)  # No providers/backend.
        module = str(path.parent)
        names = [key for block in parsed.get("locals", []) for key in block]
        locals_by_module.setdefault(module, []).extend(names)
        references_by_module.setdefault(module, set()).update(
            re.findall(r"(?<![\w.])local\.([a-zA-Z_0-9]+)", json.dumps(parsed))
        )
        current = findings(text)
        previous = subprocess.run(["git", "show", f"{base}:{name}"], capture_output=True, text=True)
        before = findings(previous.stdout) if previous.returncode == 0 else Counter()
        total.update(current)
        additions.extend((name, rule, count) for rule, count in (current - before).items())
    print(
        "Static security inventory (existing findings require live-plan review): "
        + str(dict(total))
    )
    if additions:
        raise ValueError(
            "New static security risk requires an explicitly reviewed scoped change: "
            + str(additions)
        )
