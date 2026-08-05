from __future__ import annotations

import tomllib
from pathlib import Path

import snaketracker

ROOT = Path(__file__).parents[2]

FORBIDDEN_PHASE_TWO_PATHS = (
    "src/snaketracker/domains/animals",
    "src/snaketracker/domains/enclosures",
    "src/snaketracker/domains/inventory",
    "src/snaketracker/domains/expenses",
    "src/snaketracker/domains/reminders",
    "src/snaketracker/platform/jobs",
    "src/snaketracker/platform/notifications",
)

FORBIDDEN_PHASE_TWO_DEPENDENCIES = {
    "authlib",
    "passlib",
    "pyjwt",
    "python-jose",
}


def test_phase_one_project_uses_python_313_and_src_layout() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13.14"
    bootstrap = (ROOT / "scripts/development/bootstrap.sh").read_text(encoding="utf-8")
    assert 'uv python install "$python_version"' in bootstrap
    assert (ROOT / "src/snaketracker/__init__.py").is_file()
    assert (ROOT / "src/snaketracker/py.typed").is_file()


def test_package_exposes_the_project_version() -> None:
    assert snaketracker.__version__ == "0.1.0"


def test_phase_two_has_no_later_phase_packages_or_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = {
        requirement.split("[", 1)[0].split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].lower()
        for requirement in project["project"]["dependencies"]
    }

    assert not FORBIDDEN_PHASE_TWO_DEPENDENCIES & dependencies
    assert not [path for path in FORBIDDEN_PHASE_TWO_PATHS if (ROOT / path).exists()]
