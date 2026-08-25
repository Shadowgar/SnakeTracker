from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationService,
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.application.identity import (
    AuthenticationError,
    IdentityService,
    InvalidPasswordResetError,
    PasswordResetMessage,
    PasswordResetValidationError,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"password-recovery-test-secret-32-bytes"
OLD_PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery staple"


@dataclass
class CaptureDelivery:
    messages: list[PasswordResetMessage] = field(default_factory=list)

    def deliver(self, message: PasswordResetMessage) -> None:
        self.messages.append(message)


class FailingDelivery:
    def deliver(self, message: PasswordResetMessage) -> None:
        raise OSError(f"delivery unavailable for {message.message_id}")


@dataclass
class RecoveryFixture:
    service: IdentityService
    engine: Engine
    delivery: CaptureDelivery
    owner_household_id: str
    other_household_id: str


def token_from(message: PasswordResetMessage) -> str:
    return parse_qs(urlsplit(message.reset_url).fragment)["token"][0]


@pytest.fixture
def recovery(tmp_path: Path) -> Iterator[RecoveryFixture]:
    database = tmp_path / "password-recovery.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    hasher = Argon2PasswordHasher.for_testing()
    repository = SQLAlchemyHouseholdBootstrapRepository(engine)
    owner = HouseholdBootstrapService(repository, hasher, command_hash_secret=SECRET).bootstrap(
        BootstrapCommand(
            household_name="Owner Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password=OLD_PASSWORD,
            idempotency_key="password-recovery-bootstrap",
            correlation_id=uuid4(),
        )
    )
    other = AccountRegistrationService(repository, hasher, command_hash_secret=SECRET).register(
        AccountRegistrationCommand(
            collection_name="Other Home",
            timezone="UTC",
            email="other@example.com",
            display_name="Other",
            password="other correct horse battery staple",
            idempotency_key="password-recovery-other-account",
            correlation_id=uuid4(),
        )
    )
    delivery = CaptureDelivery()
    service = IdentityService(
        SQLAlchemyIdentityRepository(engine),
        hasher,
        secret=SECRET,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=12),
        rate_limit=3,
        rate_window=timedelta(minutes=15),
        block_duration=timedelta(minutes=15),
        password_reset_delivery=delivery,
        external_origin="https://tracker.theroccos.us",
        password_reset_ttl=timedelta(minutes=45),
    )
    try:
        yield RecoveryFixture(
            service,
            engine,
            delivery,
            str(owner.household_id),
            str(other.household_id),
        )
    finally:
        engine.dispose()


def request_reset(recovery: RecoveryFixture, email: str, *, now: datetime) -> PasswordResetMessage:
    before = len(recovery.delivery.messages)
    recovery.service.request_password_reset(
        email,
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now,
    )
    assert len(recovery.delivery.messages) == before + 1
    return recovery.delivery.messages[-1]


def test_request_normalizes_email_stores_only_digest_and_does_not_enumerate(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    message = request_reset(recovery, " OWNER@EXAMPLE.COM ", now=now)
    token = token_from(message)

    recovery.service.request_password_reset(
        "missing@example.com",
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now,
    )

    assert message.reset_url.startswith("https://tracker.theroccos.us/reset-password#token=")
    assert len(token) >= 64
    assert len(recovery.delivery.messages) == 1
    with recovery.engine.connect() as connection:
        credential = connection.execute(
            text("SELECT token_hash,source FROM password_reset_credentials")
        ).one()
        stored_text = "\n".join(
            str(row)
            for table in ("password_reset_credentials", "security_audit")
            for row in connection.execute(text(f"SELECT * FROM {table}"))
        )
        audits = connection.execute(
            text(
                "SELECT outcome,details_json FROM security_audit "
                "WHERE action='password_reset.requested' ORDER BY recorded_at"
            )
        ).all()
    assert credential.token_hash != token
    assert len(credential.token_hash) == 64
    assert credential.source == "self_service"
    assert token not in stored_text
    assert message.reset_url not in stored_text
    assert audits == [
        ("success", '{"source": "self_service"}'),
        ("success", '{"source": "self_service"}'),
    ]


def test_requests_are_throttled_without_creating_a_public_state_difference(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    for attempt in range(4):
        recovery.service.request_password_reset(
            "owner@example.com",
            client_ip="192.0.2.10",
            user_agent="browser",
            correlation_id=uuid4(),
            now=now + timedelta(seconds=attempt),
        )

    assert len(recovery.delivery.messages) == 3
    with recovery.engine.connect() as connection:
        active = connection.execute(
            text(
                "SELECT count(*) FROM password_reset_credentials "
                "WHERE consumed_at IS NULL AND invalidated_at IS NULL"
            )
        ).scalar_one()
    assert active == 1


def test_unavailable_or_failed_delivery_invalidates_the_undelivered_credential(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    common = {
        "repository": SQLAlchemyIdentityRepository(recovery.engine),
        "password_hasher": Argon2PasswordHasher.for_testing(),
        "secret": SECRET,
        "idle_timeout": timedelta(minutes=30),
        "absolute_timeout": timedelta(hours=12),
        "rate_limit": 3,
        "rate_window": timedelta(minutes=15),
        "block_duration": timedelta(minutes=15),
        "external_origin": "https://tracker.theroccos.us",
    }
    without_delivery = IdentityService(**common)
    without_delivery.request_password_reset(
        "owner@example.com",
        client_ip="192.0.2.20",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now,
    )
    failed_delivery = IdentityService(**common, password_reset_delivery=FailingDelivery())
    failed_delivery.request_password_reset(
        "owner@example.com",
        client_ip="192.0.2.21",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now + timedelta(seconds=1),
    )

    with recovery.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM password_reset_credentials "
                    "WHERE consumed_at IS NULL AND invalidated_at IS NULL"
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM security_audit WHERE action='password_reset.delivery'")
            ).scalar_one()
            == 2
        )


def test_operator_recovery_requires_configured_external_origin(
    recovery: RecoveryFixture,
) -> None:
    service = IdentityService(
        SQLAlchemyIdentityRepository(recovery.engine),
        Argon2PasswordHasher.for_testing(),
        secret=SECRET,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=12),
        rate_limit=3,
        rate_window=timedelta(minutes=15),
        block_duration=timedelta(minutes=15),
    )

    with pytest.raises(RuntimeError, match="configured external origin"):
        service.initiate_operator_password_reset("owner@example.com", correlation_id=uuid4())


def test_reset_supersedes_old_token_enforces_policy_and_revokes_every_session(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    first = request_reset(recovery, "owner@example.com", now=now)
    first_token = token_from(first)
    first_session = recovery.service.login(
        "owner@example.com",
        OLD_PASSWORD,
        client_ip="127.0.0.1",
        user_agent="browser-one",
        correlation_id=uuid4(),
        now=now,
    )
    second_session = recovery.service.login(
        "owner@example.com",
        OLD_PASSWORD,
        client_ip="127.0.0.2",
        user_agent="browser-two",
        correlation_id=uuid4(),
        now=now,
    )
    second_token = token_from(
        request_reset(recovery, "owner@example.com", now=now + timedelta(minutes=1))
    )

    with pytest.raises(InvalidPasswordResetError):
        recovery.service.complete_password_reset(
            first_token,
            NEW_PASSWORD,
            NEW_PASSWORD,
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=2),
        )
    with pytest.raises(PasswordResetValidationError, match="do not match"):
        recovery.service.complete_password_reset(
            second_token,
            NEW_PASSWORD,
            "different password value",
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=2),
        )
    with pytest.raises(PasswordResetValidationError, match="12 and 1024"):
        recovery.service.complete_password_reset(
            second_token,
            "short",
            "short",
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=2),
        )

    recovery.service.complete_password_reset(
        second_token,
        NEW_PASSWORD,
        NEW_PASSWORD,
        client_ip="127.0.0.1",
        user_agent="browser",
        correlation_id=uuid4(),
        now=now + timedelta(minutes=3),
    )

    for session in (first_session, second_session):
        with pytest.raises(AuthenticationError):
            recovery.service.authenticate(session.token, now=now + timedelta(minutes=4))
    with pytest.raises(AuthenticationError):
        recovery.service.login(
            "owner@example.com",
            OLD_PASSWORD,
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=4),
        )
    assert recovery.service.login(
        "owner@example.com",
        NEW_PASSWORD,
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now + timedelta(minutes=4),
    )
    with pytest.raises(InvalidPasswordResetError):
        recovery.service.complete_password_reset(
            second_token,
            NEW_PASSWORD,
            NEW_PASSWORD,
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=5),
        )
    with recovery.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM sessions WHERE revocation_reason='password_reset'")
            ).scalar_one()
            == 2
        )
        successful_audit = connection.execute(
            text(
                "SELECT details_json FROM security_audit "
                "WHERE action='password_reset.completed' AND outcome='success'"
            )
        ).scalar_one()
    assert successful_audit == '{"sessions_revoked": 2}'
    assert NEW_PASSWORD not in successful_audit


def test_expired_malformed_and_unknown_tokens_fail_safely(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    expired = token_from(request_reset(recovery, "owner@example.com", now=now))
    for token in (expired, "malformed", "_" * 64):
        with pytest.raises(InvalidPasswordResetError, match="invalid or has expired"):
            recovery.service.complete_password_reset(
                token,
                NEW_PASSWORD,
                NEW_PASSWORD,
                client_ip=None,
                user_agent=None,
                correlation_id=uuid4(),
                now=now + timedelta(minutes=46),
            )


def test_password_reset_is_user_scoped_and_preserves_other_household(
    recovery: RecoveryFixture,
) -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    membership_before: list[tuple[str, str, str]]
    with recovery.engine.connect() as connection:
        membership_before = list(
            connection.execute(
                text(
                    "SELECT household_id,user_id,role FROM authorization_memberships "
                    "ORDER BY household_id,user_id"
                )
            ).tuples()
        )
    token = token_from(request_reset(recovery, "other@example.com", now=now))
    recovery.service.complete_password_reset(
        token,
        "other new correct horse battery staple",
        "other new correct horse battery staple",
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now + timedelta(minutes=1),
    )

    assert recovery.service.login(
        "owner@example.com",
        OLD_PASSWORD,
        client_ip=None,
        user_agent=None,
        correlation_id=uuid4(),
        now=now + timedelta(minutes=2),
    )
    with pytest.raises(AuthenticationError):
        recovery.service.login(
            "other@example.com",
            "other correct horse battery staple",
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=2),
        )
    principal = recovery.service.authenticate(
        recovery.service.login(
            "other@example.com",
            "other new correct horse battery staple",
            client_ip=None,
            user_agent=None,
            correlation_id=uuid4(),
            now=now + timedelta(minutes=2),
        ).token,
        now=now + timedelta(minutes=3),
    )
    assert str(principal.household_id) == recovery.other_household_id
    assert str(principal.household_id) != recovery.owner_household_id
    with recovery.engine.connect() as connection:
        membership_after = list(
            connection.execute(
                text(
                    "SELECT household_id,user_id,role FROM authorization_memberships "
                    "ORDER BY household_id,user_id"
                )
            ).tuples()
        )
    assert membership_after == membership_before
