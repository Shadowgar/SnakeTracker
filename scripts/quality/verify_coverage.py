#!/usr/bin/env python3
"""Enforce independent line and branch coverage thresholds."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MINIMUM_LINE_PERCENT = 90.0
MINIMUM_BRANCH_PERCENT = 85.0


def percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def main() -> int:
    report_path = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    totals = report["totals"]
    line_percent = percentage(totals["covered_lines"], totals["num_statements"])
    branch_percent = percentage(totals["covered_branches"], totals["num_branches"])
    failures: list[str] = []
    if line_percent < MINIMUM_LINE_PERCENT:
        failures.append(f"line coverage {line_percent:.2f}% is below {MINIMUM_LINE_PERCENT:.2f}%")
    if branch_percent < MINIMUM_BRANCH_PERCENT:
        failures.append(
            f"branch coverage {branch_percent:.2f}% is below {MINIMUM_BRANCH_PERCENT:.2f}%"
        )
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    print(f"coverage gates passed: lines={line_percent:.2f}% branches={branch_percent:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
