from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.identity import (
    AuthenticationError,
    IdentityService,
    LoginBlockedError,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"test-runtime-secret-at-least-32-bytes"


@pytest.fixture
def identity_service(tmp_path: Path) -> Iterator[tuple[IdentityService, Engine]]:
    database = tmp_path / "identity.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    hasher = Argon2PasswordHasher.for_testing()
    HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine), hasher, command_hash_secret=SECRET
    ).bootstrap(
        BootstrapCommand(
            household_name="Rocco's Reptiles",
            timezone="America/New_York",
            owner_email="owner@example.com",
            owner_display_name="Rocco",
            password="correct horse battery staple",
            idempotency_key="test-bootstrap-key-0001",
            correlation_id=uuid4(),
        )
    )
    service = IdentityService(
        SQLAlchemyIdentityRepository(engine),
        hasher,
        secret=SECRET,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=12),
        rate_limit=3,
        rate_window=timedelta(minutes=15),
        block_duration=timedelta(minutes=15),
    )
    try:
        yield service, engine
    finally:
        engine.dispose()


def test_login_creates_opaque_session_and_resolves_current_authorization(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)

    issued = service.login(
        "OWNER@example.com",
        "correct horse battery staple",
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now,
    )
    principal = service.authenticate(issued.token, now=now + timedelta(minutes=1))

    assert principal.display_name == "Rocco"
    assert principal.role == "owner"
    assert "household.manage" in principal.capabilities
    assert service.verify_csrf(issued.token, issued.csrf_token, now=now + timedelta(minutes=1))
    with engine.connect() as connection:
        row = connection.execute(text("SELECT token_hash, csrf_token_hash FROM sessions")).one()
        assert issued.token not in row.token_hash
        assert issued.csrf_token not in row.csrf_token_hash


def test_logout_revocation_and_expiration_reject_session(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    issued = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now,
    )

    service.logout(issued.token, correlation_id=uuid4(), now=now + timedelta(minutes=1))
    with pytest.raises(AuthenticationError):
        service.authenticate(issued.token, now=now + timedelta(minutes=2))

    expired = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now,
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sessions SET idle_expires_at=:idle WHERE revoked_at IS NULL"),
            {"idle": (now + timedelta(hours=13)).isoformat(timespec="microseconds")},
        )
    with pytest.raises(AuthenticationError):
        service.authenticate(expired.token, now=now + timedelta(hours=12, seconds=1))


def test_failed_logins_are_generic_audited_and_rate_limited(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    for attempt in range(3):
        with pytest.raises(AuthenticationError, match="Email or password is incorrect"):
            service.login(
                "owner@example.com",
                "wrong password here",
                client_ip="127.0.0.1",
                user_agent="browser",
                correlation_id=uuid4(),
                now=now + timedelta(seconds=attempt),
            )

    with pytest.raises(LoginBlockedError):
        service.login(
            "owner@example.com",
            "correct horse battery staple",
            client_ip="127.0.0.1",
            user_agent="browser",
            correlation_id=uuid4(),
            now=now + timedelta(seconds=4),
        )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM security_audit WHERE action='login' AND outcome='failure'"
                )
            ).scalar_one()
            == 3
        )


def test_current_membership_is_checked_on_every_protected_request(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    issued = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now,
    )
    with engine.begin() as connection:
        connection.execute(text("UPDATE authorization_memberships SET status='suspended'"))

    with pytest.raises(AuthenticationError):
        service.authenticate(issued.token, now=now + timedelta(minutes=1))


def test_session_rotation_revokes_old_token_and_preserves_household_context(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, _engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    issued = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now,
    )

    rotated = service.rotate_session(
        issued.token,
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now + timedelta(minutes=1),
    )

    with pytest.raises(AuthenticationError):
        service.authenticate(issued.token, now=now + timedelta(minutes=2))
    assert service.authenticate(rotated.token, now=now + timedelta(minutes=2)).household_name == (
        "Rocco's Reptiles"
    )


def test_session_is_household_bound_and_capabilities_follow_current_role(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    issued = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now,
    )
    with engine.begin() as connection:
        connection.execute(text("UPDATE authorization_memberships SET role='viewer'"))
    principal = service.authenticate(issued.token, now=now + timedelta(minutes=1))
    assert principal.capabilities == frozenset({"household.view"})

    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO household_summaries "
                "(household_id,name,timezone,source_stream_version,source_global_position,"
                "created_at,updated_at) VALUES (:id,'Other','UTC',1,999,:now,:now)"
            ),
            {"id": str(other), "now": now.isoformat()},
        )
        connection.execute(text("UPDATE sessions SET household_id=:other"), {"other": str(other)})
    with pytest.raises(AuthenticationError):
        service.authenticate(issued.token, now=now + timedelta(minutes=2))


def test_restoration_hook_invalidates_all_existing_sessions(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    issued = service.login(
        "owner@example.com",
        "correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now,
    )

    service.invalidate_sessions_after_restoration(
        correlation_id=uuid4(), now=now + timedelta(minutes=1)
    )

    with pytest.raises(AuthenticationError):
        service.authenticate(issued.token, now=now + timedelta(minutes=2))
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM sessions WHERE revocation_reason='restoration'")
            ).scalar_one()
            == 1
        )


def test_security_audit_uses_the_operation_timestamp(
    identity_service: tuple[IdentityService, Engine],
) -> None:
    service, engine = identity_service
    now = datetime(2026, 8, 5, 12, 0, 0, 123456, tzinfo=UTC)

    with pytest.raises(AuthenticationError):
        service.login(
            "owner@example.com",
            "wrong password",
            client_ip="127.0.0.1",
            user_agent="browser",
            correlation_id=uuid4(),
            now=now,
        )
    service.audit_access_denied(
        correlation_id=uuid4(),
        client_ip="127.0.0.1",
        user_agent="browser",
        now=now,
    )

    with engine.connect() as connection:
        timestamps = connection.execute(
            text("SELECT recorded_at FROM security_audit ORDER BY rowid DESC LIMIT 2")
        ).scalars()
        assert set(timestamps) == {now.isoformat(timespec="microseconds")}
