from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).parents[2]
REVISION = "0001_phase1_baseline"


def alembic_config(database: Path) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def current_revision(database: Path) -> str | None:
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    finally:
        engine.dispose()


def test_baseline_migration_upgrades_downgrades_and_reupgrades(tmp_path: Path) -> None:
    database = tmp_path / "migration.sqlite3"
    config = alembic_config(database)

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert current_revision(database) is None

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION


def test_migrations_contain_no_event_upcasters_or_product_tables() -> None:
    migration_root = ROOT / "migrations"
    assert not list(migration_root.rglob("*upcaster*"))

    migration_text = "\n".join(
        path.read_text(encoding="utf-8") for path in migration_root.rglob("*.py")
    ).lower()
    forbidden = {"animals", "domain_events", "households", "jobs", "notifications", "users"}
    assert not {name for name in forbidden if name in migration_text}
