from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
REVISION = "0004_event_platform"
PHASE_THREE_TABLES = {
    "aggregate_snapshots",
    "alembic_version",
    "authorization_memberships",
    "domain_events",
    "event_streams",
    "event_subjects",
    "household_summaries",
    "idempotency_operations",
    "login_rate_limits",
    "outbox_items",
    "projection_checkpoints",
    "projection_definitions",
    "projection_generations",
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
        assert set(inspect(engine).get_table_names()) == PHASE_THREE_TABLES
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert current_revision(database) is None

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION


def test_migrations_contain_no_event_upcasters_or_phase_four_tables() -> None:
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
        foreign_targets = {
            table: {
                foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys(table)
            }
            for table in ("authorization_memberships", "sessions", "event_subjects")
        }
        assert foreign_targets == {
            "authorization_memberships": {"household_summaries", "users"},
            "sessions": {"household_summaries", "users"},
            "event_subjects": {"domain_events"},
        }
        assert "ix_domain_events_stream" not in {
            item["name"] for item in inspector.get_indexes("domain_events")
        }
        assert {item["name"] for item in inspector.get_unique_constraints("outbox_items")} == {
            "uq_outbox_logical_handoff"
        }
        assert {
            item["name"] for item in inspector.get_unique_constraints("aggregate_snapshots")
        } == {"uq_snapshot_stream_version_schema"}
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


def test_phase_two_household_events_are_unchanged_by_phase_three_migration(
    tmp_path: Path,
) -> None:
    database = tmp_path / "phase2-upgrade.sqlite3"
    config = alembic_config(database)
    command.upgrade(config, "0003_phase2_review_hardening")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"phase3-migration-test-secret-32-bytes",
        ).bootstrap(
            BootstrapCommand(
                household_name="Migration Home",
                timezone="UTC",
                owner_email="migration@example.com",
                owner_display_name="Migration Owner",
                password="correct horse battery staple",
                idempotency_key="phase3-migration-fixture",
                correlation_id=uuid4(),
            )
        )
        with engine.connect() as connection:
            events_before = (
                connection.execute(text("SELECT * FROM domain_events ORDER BY global_position"))
                .mappings()
                .all()
            )
            subjects_before = (
                connection.execute(
                    text(
                        "SELECT * FROM event_subjects "
                        "ORDER BY event_id,subject_type,subject_id,relationship"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    upgraded = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with upgraded.connect() as connection:
            assert (
                connection.execute(text("SELECT * FROM domain_events ORDER BY global_position"))
                .mappings()
                .all()
                == events_before
            )
            assert (
                connection.execute(
                    text(
                        "SELECT * FROM event_subjects "
                        "ORDER BY event_id,subject_type,subject_id,relationship"
                    )
                )
                .mappings()
                .all()
                == subjects_before
            )
    finally:
        upgraded.dispose()
