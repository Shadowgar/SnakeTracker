#!/usr/bin/env python3
"""Guard the accepted architecture baseline and ADR decision freeze."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
BASELINE_COMMIT = "bb3ab39"
ACCEPTANCE_DATE = "2026-08-04"


def main() -> int:
    failures: list[str] = []
    adr_paths = sorted((ROOT / "docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    expected_names = {f"{number:04d}" for number in range(1, 36)}
    actual_names = {path.name[:4] for path in adr_paths}
    if actual_names != expected_names:
        failures.append("ADR catalog must contain exactly ADR-0001 through ADR-0035")
    for path in adr_paths:
        text = path.read_text(encoding="utf-8")
        if "Status: Accepted" not in text or f"Acceptance date: {ACCEPTANCE_DATE}" not in text:
            failures.append(f"{path.relative_to(ROOT)} is not accepted on {ACCEPTANCE_DATE}")

    docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    adr_index = (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    if "Status: Approved" not in docs_index or "decision freeze" not in docs_index:
        failures.append("architecture index does not record approval and decision freeze")
    if "Accepted on 2026-08-04" not in adr_index or "decision freeze is active" not in adr_index:
        failures.append("ADR index does not record acceptance and decision freeze")

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        failures.append(f"architecture baseline {BASELINE_COMMIT} is not an ancestor of HEAD")
    if failures:
        print("architecture freeze failures:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"architecture freeze passed: {len(adr_paths)} accepted ADRs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
