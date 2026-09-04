from __future__ import annotations

import inspect
import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.identity import IdentityService, PasswordResetMessage
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.identity.password_reset_delivery import (
    LocalFilePasswordResetDelivery,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.operations import account_recovery
from snaketracker.operations.account_recovery import initiate_operator_recovery

ROOT = Path(__file__).parents[3]
SECRET = "operator-password-recovery-secret-32-bytes"


def prepared_settings(tmp_path: Path) -> Settings:
    database = tmp_path / "operator-recovery.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET.encode(),
        ).bootstrap(
            BootstrapCommand(
                household_name="Operator Recovery Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="operator-recovery-bootstrap",
                correlation_id=uuid4(),
            )
        )
    finally:
        engine.dispose()
    return Settings(
        environment=Environment.TEST,
        database_path=database,
        external_origin="https://tracker.theroccos.us",
        runtime_secret=SECRET,
        session_cookie_secure=False,
    )


def test_operator_recovery_creates_audited_one_time_flow_without_password_argument(
    tmp_path: Path,
) -> None:
    settings = prepared_settings(tmp_path)
    url = initiate_operator_recovery(settings, email=" OWNER@example.com ")

    assert url is not None
    assert url.startswith("https://tracker.theroccos.us/reset-password#token=")
    token = parse_qs(urlsplit(url).fragment)["token"][0]
    assert list(inspect.signature(initiate_operator_recovery).parameters) == ["settings", "email"]
    engine = create_sqlite_engine(settings.database_path, require_local_storage=False)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT token_hash,source FROM password_reset_credentials")
            ).one()
            audit = connection.execute(
                text(
                    "SELECT details_json FROM security_audit "
                    "WHERE action='password_reset.requested' ORDER BY recorded_at DESC LIMIT 1"
                )
            ).scalar_one()
        assert row.source == "operator"
        assert row.token_hash != token
        assert token not in audit

        service = IdentityService(
            SQLAlchemyIdentityRepository(engine),
            Argon2PasswordHasher.for_testing(),
            secret=SECRET.encode(),
            idle_timeout=timedelta(minutes=30),
            absolute_timeout=timedelta(hours=12),
            rate_limit=5,
            rate_window=timedelta(minutes=15),
            block_duration=timedelta(minutes=15),
            external_origin="https://tracker.theroccos.us",
        )
        service.complete_password_reset(
            token,
            "operator supplied new secure password",
            "operator supplied new secure password",
            client_ip=None,
            user_agent="operator-test",
            correlation_id=uuid4(),
        )
    finally:
        engine.dispose()


def test_operator_recovery_handles_unknown_account_without_creating_credential(
    tmp_path: Path,
) -> None:
    settings = prepared_settings(tmp_path)

    assert initiate_operator_recovery(settings, email="missing@example.com") is None
    engine = create_sqlite_engine(settings.database_path, require_local_storage=False)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM password_reset_credentials")
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_operator_command_reports_generated_and_absent_urls_without_password_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(account_recovery, "load_settings", object)
    monkeypatch.setattr(
        account_recovery,
        "initiate_operator_recovery",
        lambda _settings, *, email: (
            "https://tracker.theroccos.us/reset-password#token=one-time"
            if email == "known"
            else None
        ),
    )
    monkeypatch.setattr("sys.argv", ["account-recovery", "known"])
    assert account_recovery.main() == 0
    assert "#token=one-time" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["account-recovery", "missing"])
    assert account_recovery.main() == 0
    assert capsys.readouterr().out == "No reset URL was generated.\n"


def test_operator_recovery_requires_runtime_secret_and_origin(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="runtime secret"):
        initiate_operator_recovery(
            Settings(
                environment=Environment.TEST,
                database_path=tmp_path / "unused.sqlite3",
                external_origin="https://tracker.theroccos.us",
                runtime_secret=None,
            ),
            email="owner@example.com",
        )
    with pytest.raises(RuntimeError, match="external origin"):
        initiate_operator_recovery(
            Settings(
                environment=Environment.TEST,
                database_path=tmp_path / "unused.sqlite3",
                runtime_secret=SECRET,
            ),
            email="owner@example.com",
        )


def test_local_delivery_writes_private_artifact_and_rejects_production(tmp_path: Path) -> None:
    destination = tmp_path / "messages"
    adapter = LocalFilePasswordResetDelivery(destination, environment="test")
    message = PasswordResetMessage(
        uuid4(),
        "owner@example.com",
        "https://tracker.theroccos.us/reset-password#token=secret-for-delivery-only",
        datetime.now(UTC),
    )

    adapter.deliver(message)

    artifact = next(destination.iterdir())
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["reset_url"] == message.reset_url
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="restricted to development and test"):
        LocalFilePasswordResetDelivery(destination, environment="production")
