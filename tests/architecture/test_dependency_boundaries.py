from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
CHECKER = ROOT / "scripts/quality/verify_architecture.py"


def run_checker(source_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(source_root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_phase_one_packages_satisfy_dependency_rules() -> None:
    result = run_checker(ROOT / "src")

    assert result.returncode == 0, result.stderr


def test_checker_rejects_infrastructure_importing_presentation(tmp_path: Path) -> None:
    module = tmp_path / "snaketracker/infrastructure/example.py"
    module.parent.mkdir(parents=True)
    module.write_text("from snaketracker.presentation import health\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "infrastructure cannot import presentation" in result.stderr
