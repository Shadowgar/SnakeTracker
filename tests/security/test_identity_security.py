from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

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


def identity_service(tmp_path: Path) -> tuple[IdentityService, object]:
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
    return service, engine


def test_login_creates_opaque_session_and_resolves_current_authorization(tmp_path: Path) -> None:
    service, engine = identity_service(tmp_path)
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
    assert service.verify_csrf(issued.token, issued.csrf_token)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT token_hash, csrf_token_hash FROM sessions")).one()
        assert issued.token not in row.token_hash
        assert issued.csrf_token not in row.csrf_token_hash
    engine.dispose()


def test_logout_revocation_and_expiration_reject_session(tmp_path: Path) -> None:
    service, engine = identity_service(tmp_path)
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
    with pytest.raises(AuthenticationError):
        service.authenticate(expired.token, now=now + timedelta(hours=13))
    engine.dispose()


def test_failed_logins_are_generic_audited_and_rate_limited(tmp_path: Path) -> None:
    service, engine = identity_service(tmp_path)
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
    engine.dispose()


def test_current_membership_is_checked_on_every_protected_request(tmp_path: Path) -> None:
    service, engine = identity_service(tmp_path)
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
    engine.dispose()
