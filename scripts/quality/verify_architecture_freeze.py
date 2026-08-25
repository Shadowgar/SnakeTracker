#!/usr/bin/env python3
"""Guard the accepted architecture baseline and ADR decision freeze."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
BASELINE_COMMIT = "bb3ab39"
ACCEPTANCE_DATES = {
    **{f"{number:04d}": "2026-08-04" for number in range(1, 36)},
    "0036": "2026-08-05",
    "0037": "2026-08-05",
    "0038": "2026-08-10",
    "0039": "2026-08-11",
    "0040": "2026-08-16",
    "0041": "2026-08-24",
}
APPROVED_AMENDMENT_PATHS = {
    "docs/README.md",
    "docs/adr/README.md",
    "docs/adr/0036-development-and-pi-deployment-qualification.md",
    "docs/adr/0037-phase-order-minimal-household-events.md",
    "docs/adr/0038-scheduling-and-husbandry-reference-profiles.md",
    "docs/adr/0039-multispecies-animal-capabilities.md",
    "docs/adr/0040-trusted-local-demo-household-provisioning.md",
    "docs/adr/0041-four-group-capability-expansion-and-neutral-molt-contracts.md",
    "docs/architecture/domain-catalog.md",
    "docs/architecture/database-schema.md",
    "docs/architecture/event-catalog.md",
    "docs/architecture/projection-catalog.md",
    "docs/architecture/system-architecture.md",
    "docs/operations/runtime-operations.md",
    "docs/quality/representative-dataset.md",
    "docs/requirements/traceability-matrix.md",
    "docs/roadmap/milestones.md",
    "docs/ux/information-architecture.md",
}
PROTECTED_PREFIXES = (
    "docs/adr/",
    "docs/architecture/",
    "docs/quality/",
    "docs/requirements/",
    "docs/roadmap/",
    "docs/security/",
    "docs/ux/",
)
PROTECTED_FILES = {
    "docs/README.md",
    "docs/operations/backup-and-restoration.md",
    "docs/operations/runtime-operations.md",
}


def protected_architecture_changes(paths: set[str]) -> set[str]:
    return {
        path for path in paths if path in PROTECTED_FILES or path.startswith(PROTECTED_PREFIXES)
    }


def main() -> int:
    failures: list[str] = []
    adr_paths = sorted((ROOT / "docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    expected_names = set(ACCEPTANCE_DATES)
    actual_names = {path.name[:4] for path in adr_paths}
    if actual_names != expected_names:
        failures.append("ADR catalog must contain exactly ADR-0001 through ADR-0041")
    for path in adr_paths:
        text = path.read_text(encoding="utf-8")
        acceptance_date = ACCEPTANCE_DATES[path.name[:4]]
        if "Status: Accepted" not in text or f"Acceptance date: {acceptance_date}" not in text:
            failures.append(f"{path.relative_to(ROOT)} is not accepted on {acceptance_date}")

    docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    adr_index = (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    if "Status: Approved" not in docs_index or "decision freeze" not in docs_index:
        failures.append("architecture index does not record approval and decision freeze")
    if (
        "Accepted on 2026-08-04" not in adr_index
        or "Accepted on 2026-08-05" not in adr_index
        or "decision freeze is active" not in adr_index
    ):
        failures.append("ADR index does not record acceptance and decision freeze")

    diff = subprocess.run(
        ["git", "diff", "--name-only", BASELINE_COMMIT, "--", "docs"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        failures.append("could not compare architecture documents to the baseline")
    else:
        changes = protected_architecture_changes(set(diff.stdout.splitlines()))
        unapproved_changes = changes - APPROVED_AMENDMENT_PATHS
        if unapproved_changes:
            failures.append(
                "accepted architecture changed without updating the freeze gate: "
                + ", ".join(sorted(unapproved_changes))
            )

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
