from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application import household_bootstrap
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


def demo_service(engine, *, environment: str = "development"):
    service_type = getattr(household_bootstrap, "DemoHouseholdProvisioningService", None)
    assert service_type is not None, "trusted local demo provisioning service is missing"
    return service_type(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-demo-command-secret-at-least-32b",
        environment=environment,
    )


def provision(service):
    command_type = getattr(household_bootstrap, "DemoHouseholdProvisioningCommand", None)
    assert command_type is not None, "trusted local demo provisioning command is missing"
    return service.provision(command_type(password="m6-demo-local-only-password"))


@pytest.mark.parametrize("environment", ["production", "", "staging"])
def test_demo_provisioning_hard_fails_outside_allow_list(tmp_path: Path, environment: str) -> None:
    engine = migrated_engine(tmp_path / f"forbidden-{environment or 'empty'}.sqlite3")

    with pytest.raises(RuntimeError, match="not permitted"):
        provision(demo_service(engine, environment=environment))

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 0
    engine.dispose()


def test_demo_provisioning_is_atomic_canonical_and_idempotent(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path / "trusted-local.sqlite3")
    service = demo_service(engine)

    first = provision(service)
    second = provision(service)

    assert second == first
    assert str(first.household_id) == household_bootstrap.DEMO_HOUSEHOLD_ID
    assert str(first.user_id) == household_bootstrap.DEMO_OWNER_USER_ID
    with engine.connect() as connection:
        user = (
            connection.execute(
                text("SELECT email_normalized, status FROM users WHERE user_id=:user_id"),
                {"user_id": str(first.user_id)},
            )
            .mappings()
            .one()
        )
        assert user == {"email_normalized": "demo@carekeeper.local", "status": "active"}
        events = (
            connection.execute(
                text(
                    "SELECT event_type, schema_version, stream_version, checksum "
                    "FROM domain_events WHERE household_id=:household_id ORDER BY stream_version"
                ),
                {"household_id": str(first.household_id)},
            )
            .mappings()
            .all()
        )
        assert [(row["event_type"], row["schema_version"]) for row in events] == [
            ("household.created", 1),
            ("household.owner_added", 1),
        ]
        assert [row["stream_version"] for row in events] == [1, 2]
        assert all(len(row["checksum"]) == 64 for row in events)
        membership = connection.execute(
            text(
                "SELECT role, status FROM authorization_memberships "
                "WHERE household_id=:household_id AND user_id=:user_id"
            ),
            {"household_id": str(first.household_id), "user_id": str(first.user_id)},
        ).one()
        assert membership == ("owner", "active")
        operation = connection.execute(
            text(
                "SELECT operation_scope, status FROM idempotency_operations "
                "WHERE household_id=:household_id"
            ),
            {"household_id": str(first.household_id)},
        ).one()
        assert operation == ("household.demo_provision", "completed")
        audit = connection.execute(
            text(
                "SELECT category, action, outcome FROM security_audit "
                "WHERE household_id=:household_id"
            ),
            {"household_id": str(first.household_id)},
        ).one()
        assert audit == ("identity", "household.demo_provision", "success")
    engine.dispose()


def test_demo_provisioning_can_add_household_after_real_bootstrap(tmp_path: Path) -> None:
    from tests.integration.test_household_bootstrap import command_for

    engine = migrated_engine(tmp_path / "real-and-demo.sqlite3")
    real = household_bootstrap.HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    ).bootstrap(command_for())

    demo = provision(demo_service(engine))

    assert demo.household_id != real.household_id
    assert demo.user_id != real.user_id
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 2
        household_count = connection.execute(
            text("SELECT count(*) FROM household_summaries")
        ).scalar_one()
        assert household_count == 2
        assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 4
    engine.dispose()


def test_demo_provisioning_fails_closed_on_reserved_identity_conflict(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path / "conflict.sqlite3")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (user_id,email_normalized,display_name,password_hash,"
                "password_scheme,status,created_at,updated_at) VALUES "
                "(:user_id,'demo@carekeeper.local','Conflicting user','hash','argon2id','active',"
                "'2026-08-16T00:00:00+00:00','2026-08-16T00:00:00+00:00')"
            ),
            {"user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
        )

    with pytest.raises(RuntimeError, match="conflict"):
        provision(demo_service(engine))

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM security_audit")).scalar_one() == 0
    engine.dispose()
