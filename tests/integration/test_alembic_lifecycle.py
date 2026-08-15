from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
REVISION = "0011_product_experience"
PHASE_FIVE_TABLES = {
    "aggregate_snapshots",
    "alembic_version",
    "animal_current",
    "attachment_staging",
    "attachment_versions",
    "authorization_memberships",
    "backup_leases",
    "backup_requests",
    "backup_runs",
    "backup_schedules",
    "domain_events",
    "delivery_attempts",
    "enclosure_current",
    "expense_current",
    "event_streams",
    "event_subjects",
    "household_summaries",
    "idempotency_operations",
    "inventory_balance",
    "inventory_consumption_links",
    "inventory_consumption_allocations",
    "jobs",
    "login_rate_limits",
    "local_notification_operations",
    "notification_intents",
    "outbox_items",
    "projection_checkpoints",
    "projection_definitions",
    "projection_generations",
    "reminder_facts",
    "reminder_rule_current",
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


def test_multispecies_migration_blocks_downgrade_when_v2_events_exist(tmp_path: Path) -> None:
    database = tmp_path / "multispecies-downgrade-guard.sqlite3"
    config = alembic_config(database)
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"m55-migration-guard-secret-32-bytes",
        ).bootstrap(
            BootstrapCommand(
                household_name="Mixed Migration Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="m55-migration-bootstrap",
                correlation_id=uuid4(),
            )
        )
        AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        ).register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="m55-migration-spider",
                name="Charlotte",
                species="Grammostola pulchra",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
                animal_type="spider",
            )
        )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match=r"M5\.5 downgrade blocked"):
        command.downgrade(config, "0009_operational_workflows")
    assert current_revision(database) == "0010_multispecies_foundation"


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
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == PHASE_FIVE_TABLES
        definition_columns = {
            column["name"] for column in inspector.get_columns("projection_definitions")
        }
        generation_columns = {
            column["name"] for column in inspector.get_columns("projection_generations")
        }
        assert {"source_kind", "freshness_threshold_seconds"} <= definition_columns
        assert "source_manifest_checksum" in generation_columns
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert current_revision(database) is None

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION


def test_phase_five_downgrade_normalizes_new_outbox_states(tmp_path: Path) -> None:
    database = tmp_path / "outbox-downgrade.sqlite3"
    config = alembic_config(database)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO outbox_items "
                    "(outbox_id,household_id,kind,payload_contract,schema_version,logical_key,"
                    "payload_json,correlation_id,available_at,state,created_at) VALUES "
                    "(:outbox_id,:household_id,'test','test.contract',1,:logical_key,'{}',"
                    ":correlation_id,'2026-08-11T12:00:00.000000Z','handed_off',"
                    "'2026-08-11T12:00:00.000000Z')"
                ),
                {
                    "outbox_id": str(uuid4()),
                    "household_id": str(uuid4()),
                    "logical_key": f"downgrade-{uuid4()}",
                    "correlation_id": str(uuid4()),
                },
            )
    finally:
        engine.dispose()

    command.downgrade(config, "0008_local_backups")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT state FROM outbox_items")).scalar_one() == "pending"
            )
    finally:
        engine.dispose()


def test_multispecies_migration_backfills_existing_animals_as_snake_v1(tmp_path: Path) -> None:
    database = tmp_path / "multispecies-backfill.sqlite3"
    config = alembic_config(database)
    command.upgrade(config, "0009_operational_workflows")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    animal_id = uuid4()
    household_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO animal_current "
                    "(household_id,animal_id,name,species,status,stream_version,"
                    "last_event_id,updated_at) VALUES "
                    "(:household_id,:animal_id,'Legacy','Python regius','active',1,:event_id,"
                    "'2026-08-11T12:00:00.000000+00:00')"
                ),
                {
                    "household_id": str(household_id),
                    "animal_id": str(animal_id),
                    "event_id": str(uuid4()),
                },
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("animal_current")}
        assert {"animal_type", "capability_profile_version"} <= columns
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT animal_type,capability_profile_version FROM animal_current "
                    "WHERE animal_id=:animal_id"
                ),
                {"animal_id": str(animal_id)},
            ).one() == ("snake", 1)
    finally:
        engine.dispose()

    command.downgrade(config, "0009_operational_workflows")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        remaining = {column["name"] for column in inspect(engine).get_columns("animal_current")}
        assert remaining.isdisjoint({"animal_type", "capability_profile_version"})
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    assert current_revision(database) == REVISION


def test_migrations_contain_no_event_upcasters() -> None:
    migration_root = ROOT / "migrations"
    assert not list(migration_root.rglob("*upcaster*"))


def test_product_experience_migration_blocks_downgrade_with_active_m6_definitions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "m6-downgrade-guard.sqlite3"
    config = alembic_config(database)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projection_definitions "
                    "(projection_name,projection_schema_version,handler_version,"
                    "consistency_class,rebuild_group,physical_identifier,source_kind,"
                    "freshness_threshold_seconds,updated_at) VALUES "
                    "('global_search_fts',1,1,'asynchronous','search','search','event_stream',"
                    "60,'2026-08-15T12:00:00.000000+00:00')"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="M6 downgrade blocked"):
        command.downgrade(config, "0010_multispecies_foundation")
    assert current_revision(database) == REVISION


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
        assert {item["name"] for item in inspector.get_unique_constraints("jobs")} == {
            "uq_jobs_logical_operation"
        }
        assert {
            item["name"] for item in inspector.get_unique_constraints("notification_intents")
        } == {"uq_notification_intent_occurrence_recipient_channel"}
        assert {item["name"] for item in inspector.get_unique_constraints("delivery_attempts")} == {
            "uq_delivery_attempt_job_attempt_lease"
        }
        assert {
            item["name"] for item in inspector.get_unique_constraints("aggregate_snapshots")
        } == {"uq_snapshot_stream_version_schema"}
        definition_foreign_keys = inspector.get_foreign_keys("projection_definitions")
        assert any(
            foreign_key["constrained_columns"] == ["projection_name", "active_generation_id"]
            and foreign_key["referred_table"] == "projection_generations"
            and foreign_key["referred_columns"] == ["projection_name", "generation_id"]
            for foreign_key in definition_foreign_keys
        )
        checkpoint_foreign_keys = inspector.get_foreign_keys("projection_checkpoints")
        assert any(
            foreign_key["constrained_columns"] == ["projection_name", "generation_id"]
            and foreign_key["referred_table"] == "projection_generations"
            and foreign_key["referred_columns"] == ["projection_name", "generation_id"]
            for foreign_key in checkpoint_foreign_keys
        )
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
