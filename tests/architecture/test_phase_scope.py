from __future__ import annotations

import tomllib
from pathlib import Path

import snaketracker

ROOT = Path(__file__).parents[2]

FORBIDDEN_PHASE_ONE_PATHS = (
    "src/snaketracker/domains",
    "src/snaketracker/platform/auth",
    "src/snaketracker/platform/events",
    "src/snaketracker/platform/jobs",
    "src/snaketracker/platform/notifications",
    "src/snaketracker/static",
)

FORBIDDEN_PHASE_ONE_DEPENDENCIES = {
    "authlib",
    "jinja2",
    "passlib",
    "pyjwt",
    "python-jose",
}


def test_phase_one_project_uses_python_313_and_src_layout() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert (ROOT / "src/snaketracker/__init__.py").is_file()
    assert (ROOT / "src/snaketracker/py.typed").is_file()


def test_package_exposes_the_project_version() -> None:
    assert snaketracker.__version__ == "0.1.0"


def test_phase_one_has_no_phase_two_packages_or_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = {
        requirement.split("[", 1)[0].split("=", 1)[0].split("<", 1)[0].lower()
        for requirement in project["project"]["dependencies"]
    }

    assert not FORBIDDEN_PHASE_ONE_DEPENDENCIES & dependencies
    assert not [path for path in FORBIDDEN_PHASE_ONE_PATHS if (ROOT / path).exists()]
