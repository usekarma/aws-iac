"""Compatibility wrapper for the aws-config contract checker.

The repository-level tests import this module directly from the project root.
The actual implementation intentionally lives under scripts/ to keep the repo
organized, but the root module must remain importable for deterministic tests.
"""

from scripts.check_config_contract import check_compatibility, main

__all__ = ["check_compatibility", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
