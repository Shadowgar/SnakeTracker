from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.household_bootstrap import HouseholdBootstrapService
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[3]


def load_adapter() -> ModuleType:
    module = ROOT / "src/snaketracker/operations/demo_household.py"
    spec = importlib.util.spec_from_file_location("demo_household_operation", module)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def test_trusted_demo_provisioner_has_internal_operation_adapter(tmp_path: Path) -> None:
    module = ROOT / "src/snaketracker/operations/demo_household.py"

    assert module.is_file()
    adapter = load_adapter()
    database = tmp_path / "demo-operation.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")

    result = adapter.provision_demo_household(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            runtime_secret="test-operation-runtime-secret-at-least-32b",
            session_cookie_secure=False,
        ),
        password="m6-demo-local-only-password",
    )

    from sqlite3 import connect

    with connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM users WHERE user_id=?", (str(result.user_id),)
        ).fetchone() == (1,)


def test_trusted_demo_provisioner_requires_runtime_secret(tmp_path: Path) -> None:
    adapter = load_adapter()

    with pytest.raises(RuntimeError, match="requires the runtime secret"):
        adapter.provision_demo_household(
            Settings(
                environment=Environment.TEST,
                database_path=tmp_path / "never-created.sqlite3",
                runtime_secret=None,
                session_cookie_secure=False,
            ),
            password="m6-demo-local-only-password",
        )


def test_demo_operation_main_requires_password_and_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    adapter = load_adapter()
    monkeypatch.delenv("SNAKETRACKER_DEMO_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="SNAKETRACKER_DEMO_PASSWORD"):
        adapter.main()

    monkeypatch.setenv("SNAKETRACKER_DEMO_PASSWORD", "local-only-password")
    monkeypatch.setattr(adapter, "load_settings", lambda: object())
    monkeypatch.setattr(
        adapter,
        "provision_demo_household",
        lambda _settings, *, password: SimpleNamespace(household_id="reserved-demo-id"),
    )

    assert adapter.main() == 0
    assert (
        "trusted local demo household ready: household_id=reserved-demo-id"
        in capsys.readouterr().out
    )


def test_bootstrap_service_rejects_short_command_hash_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HouseholdBootstrapService(object(), object(), command_hash_secret=b"too-short")  # type: ignore[arg-type]
