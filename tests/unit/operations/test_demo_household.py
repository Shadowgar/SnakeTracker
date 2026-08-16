from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import command
from alembic.config import Config

from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[3]


def test_trusted_demo_provisioner_has_internal_operation_adapter(tmp_path: Path) -> None:
    module = ROOT / "src/snaketracker/operations/demo_household.py"

    assert module.is_file()
    spec = importlib.util.spec_from_file_location("demo_household_operation", module)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
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
