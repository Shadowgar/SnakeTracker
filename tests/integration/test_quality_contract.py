from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
SHA_PIN = re.compile(r"uses:\s+[\w.-]+/[\w.-]+@[0-9a-f]{40}(?:\s|$)")


def test_workflows_are_least_privilege_and_immutably_pinned() -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    workflows = sorted(workflow_dir.glob("*.yml"))
    assert {path.name for path in workflows} == {"container.yml", "quality.yml"}

    for path in workflows:
        content = path.read_text(encoding="utf-8")
        uses_lines = [line.strip() for line in content.splitlines() if "uses:" in line]
        assert uses_lines
        assert all(SHA_PIN.search(line) for line in uses_lines)
        assert "permissions:\n  contents: read" in content
        assert "pull_request_target:" not in content


def test_quality_workflow_delegates_to_frozen_local_gate() -> None:
    workflow = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")

    assert "uv sync --frozen" in workflow
    assert "./scripts/quality/check.sh" in workflow
    assert "retention-days: 14" in workflow
    assert "dependency-review-action" not in workflow


def test_container_workflow_builds_both_target_architectures() -> None:
    workflow = (ROOT / ".github/workflows/container.yml").read_text(encoding="utf-8")

    assert "linux/amd64,linux/arm64" in workflow
    assert "push: false" in workflow
    assert "secrets:" not in workflow


def test_coverage_gate_enforces_lines_and_branches_independently(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "covered_lines": 90,
                    "num_statements": 100,
                    "covered_branches": 84,
                    "num_branches": 100,
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/quality/verify_coverage.py"), str(report)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "branch coverage 84.00% is below 85.00%" in result.stderr


def test_documentation_links_and_architecture_freeze_are_current() -> None:
    for script in ("verify_docs_links.py", "verify_architecture_freeze.py"):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/quality" / script)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
