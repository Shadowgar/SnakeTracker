from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    BootstrapConflictError,
    HouseholdBootstrapService,
)
from snaketracker.bootstrap.compatibility import CompatibilityMode, inspect_startup_compatibility
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]


def migrated_engine(database: Path):
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return create_sqlite_engine(database, require_local_storage=False)


def command_for(key: str = "setup-retry-key-1") -> BootstrapCommand:
    return BootstrapCommand(
        household_name="Rocco's Reptiles",
        timezone="America/New_York",
        owner_email="Owner@Example.com",
        owner_display_name="Rocco",
        password="correct horse battery staple",
        idempotency_key=key,
        correlation_id=uuid4(),
    )


def test_bootstrap_commits_identity_events_projection_and_idempotency(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path / "bootstrap.sqlite3")
    service = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    )

    result = service.bootstrap(command_for())

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        events = (
            connection.execute(
                text(
                    "SELECT event_type, stream_version, correlation_id, causation_id "
                    "FROM domain_events ORDER BY stream_version"
                )
            )
            .mappings()
            .all()
        )
        assert [item["event_type"] for item in events] == [
            "household.created",
            "household.owner_added",
        ]
        assert [item["stream_version"] for item in events] == [1, 2]
        assert events[1]["causation_id"] is not None
        membership = (
            connection.execute(
                text(
                    "SELECT role, status, source_stream_version FROM authorization_memberships "
                    "WHERE household_id=:household_id AND user_id=:user_id"
                ),
                {"household_id": str(result.household_id), "user_id": str(result.user_id)},
            )
            .mappings()
            .one()
        )
        assert membership == {"role": "owner", "status": "active", "source_stream_version": 2}
        operation = (
            connection.execute(
                text("SELECT status, stored_result_json FROM idempotency_operations")
            )
            .mappings()
            .one()
        )
        assert operation["status"] == "completed"
        assert json.loads(operation["stored_result_json"])["household_id"] == str(
            result.household_id
        )
    engine.dispose()


def test_equivalent_bootstrap_retry_returns_stored_result_without_duplicates(
    tmp_path: Path,
) -> None:
    engine = migrated_engine(tmp_path / "retry.sqlite3")
    service = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    )
    first = service.bootstrap(command_for())

    second = service.bootstrap(command_for())

    assert second == first
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
    engine.dispose()


def test_bootstrap_retry_with_different_command_is_conflict(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path / "conflict.sqlite3")
    service = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    )
    service.bootstrap(command_for())
    changed = replace(command_for(), household_name="Different")

    with pytest.raises(BootstrapConflictError):
        service.bootstrap(changed)

    engine.dispose()


def test_bootstrap_rolls_back_every_record_on_projection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = migrated_engine(tmp_path / "rollback.sqlite3")
    repository = SQLAlchemyHouseholdBootstrapRepository(engine)
    service = HouseholdBootstrapService(
        repository,
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    )
    monkeypatch.setattr(repository, "_insert_membership", lambda *_args, **_kwargs: 1 / 0)

    with pytest.raises(ZeroDivisionError):
        service.bootstrap(command_for())

    with engine.connect() as connection:
        for table in (
            "users",
            "domain_events",
            "household_summaries",
            "authorization_memberships",
            "idempotency_operations",
        ):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
    engine.dispose()


def test_unknown_household_contract_forces_safe_recovery_mode(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path / "unknown-contract.sqlite3")
    service = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    )
    service.bootstrap(command_for())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE domain_events SET event_type='household.future' WHERE stream_version=2")
        )

    report = inspect_startup_compatibility(engine)

    assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
    assert report.reason_code == "household_event_contract_unknown"
    engine.dispose()
