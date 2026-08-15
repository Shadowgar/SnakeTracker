from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

import snaketracker

ROOT = Path(__file__).parents[2]

FORBIDDEN_PHASE_SIX_PATHS = (
    "src/snaketracker/domains/reports",
    "src/snaketracker/platform/search",
    "src/snaketracker/platform/analytics",
    "src/snaketracker/presentation/pwa",
)

FORBIDDEN_IDENTITY_DEPENDENCIES = {
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


def test_phase_five_has_no_phase_six_packages_or_unapproved_identity_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = {
        canonicalize_name(Requirement(requirement).name)
        for requirement in project["project"]["dependencies"]
    }

    assert not FORBIDDEN_IDENTITY_DEPENDENCIES & dependencies
    assert not [path for path in FORBIDDEN_PHASE_SIX_PATHS if (ROOT / path).exists()]


def test_reserved_synthetic_event_namespace_is_absent_from_production_and_migrations() -> None:
    production_roots = (ROOT / "src", ROOT / "migrations")
    offending: list[Path] = []
    for root in production_roots:
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".py", ".sql"}
                and "__snaketracker_test__." in path.read_text(encoding="utf-8")
            ):
                offending.append(path.relative_to(ROOT))

    assert offending == []


def test_runtime_backup_adapter_is_not_hidden_by_artifact_ignore_rule() -> None:
    ignore_rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "backups/" not in ignore_rules
    assert "/backups/" in ignore_rules


def test_m5_5_production_capability_registry_is_closed_to_approved_profiles() -> None:
    from snaketracker.domains.animals.capabilities import animal_capability_registry

    assert animal_capability_registry.identities == ("snake.v1", "spider.v1")
