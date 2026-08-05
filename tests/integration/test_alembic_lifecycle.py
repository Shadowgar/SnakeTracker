from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).parents[2]
REVISION = "0002_identity_household"
PHASE_TWO_TABLES = {
    "alembic_version",
    "authorization_memberships",
    "domain_events",
    "event_streams",
    "event_subjects",
    "household_summaries",
    "idempotency_operations",
    "login_rate_limits",
    "security_audit",
    "sessions",
    "users",
}


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
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA auto_vacuum").scalar_one() == 2
    finally:
        engine.dispose()

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        assert set(inspect(engine).get_table_names()) == PHASE_TWO_TABLES
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert current_revision(database) is None

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION


def test_migrations_contain_no_event_upcasters_or_later_phase_tables() -> None:
    migration_root = ROOT / "migrations"
    assert not list(migration_root.rglob("*upcaster*"))

    migration_text = "\n".join(
        path.read_text(encoding="utf-8") for path in migration_root.rglob("*.py")
    ).lower()
    forbidden = {
        "animals",
        "enclosures",
        "inventory",
        "expenses",
        "jobs",
        "notifications",
        "snapshots",
        "projection_generations",
    }
    assert not {name for name in forbidden if name in migration_text}


def test_identity_schema_has_required_uniqueness_and_foreign_keys(tmp_path: Path) -> None:
    database = tmp_path / "constraints.sqlite3"
    command.upgrade(alembic_config(database), "head")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        inspector = inspect(engine)
        assert {item["name"] for item in inspector.get_unique_constraints("users")} == {
            "uq_users_email_normalized"
        }
        assert {item["name"] for item in inspector.get_unique_constraints("sessions")} == {
            "uq_sessions_token_hash"
        }
        assert len(inspector.get_foreign_keys("authorization_memberships")) == 2
        assert len(inspector.get_foreign_keys("sessions")) == 1
        assert len(inspector.get_foreign_keys("event_subjects")) == 1
    finally:
        engine.dispose()


def test_schema_avoids_json_functions_unsafe_on_minimum_sqlite(tmp_path: Path) -> None:
    database = tmp_path / "portable-schema.sqlite3"
    command.upgrade(alembic_config(database), "head")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.connect() as connection:
            schema = "\n".join(
                str(value)
                for value in connection.execute(
                    text("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
                ).scalars()
            )
        assert "json_valid(" not in schema
    finally:
        engine.dispose()
