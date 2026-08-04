from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]
MODULE_PATH = ROOT / "scripts/quality/verify_architecture_freeze.py"
SPEC = importlib.util.spec_from_file_location("verify_architecture_freeze", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
freeze = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = freeze
SPEC.loader.exec_module(freeze)


def test_protected_architecture_changes_exclude_phase_evidence_and_plans() -> None:
    changed = freeze.protected_architecture_changes(
        {
            "docs/architecture/system-architecture.md",
            "docs/adr/0035-release-gates-and-internal-baseline.md",
            "docs/evidence/m1-platform/README.md",
            "docs/plans/phase1.md",
        }
    )

    assert changed == {
        "docs/architecture/system-architecture.md",
        "docs/adr/0035-release-gates-and-internal-baseline.md",
    }
