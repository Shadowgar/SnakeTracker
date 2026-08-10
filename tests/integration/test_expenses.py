from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.expenses import (
    CorrectExpenseCommand,
    ExpenseAuthorizationError,
    ExpenseService,
    ExpenseValidationError,
    RecordExpenseCommand,
    VoidExpenseCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.identity import ROLE_CAPABILITIES
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.expenses.projections import SQLAlchemyExpenseCurrentProjection
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.store import ExpectedVersionConflictError, StreamKey

ROOT = Path(__file__).parents[2]
SECRET = b"phase5-expense-test-secret-32-bytes"


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "expenses.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=SECRET,
    ).bootstrap(
        BootstrapCommand(
            household_name="Expense Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="phase5-expense-bootstrap",
            correlation_id=uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    projection = SQLAlchemyExpenseCurrentProjection(engine)
    return engine, bootstrap, store, ExpenseService(store, projection), projection


def test_expense_correction_and_void_preserve_history_and_effective_total(tmp_path: Path) -> None:
    engine, bootstrap, store, service, projection = _setup(tmp_path)
    try:
        recorded = service.record(
            RecordExpenseCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                correlation_id=uuid4(),
                idempotency_key="expense-record-vet",
                amount_minor=4500,
                currency="usd",
                category="Veterinary",
                payee="Reptile Vet",
                reference="INV-10",
                notes="Annual exam",
                occurred_at=datetime(2026, 8, 1, 14, 30, tzinfo=UTC),
            )
        )
        corrected = service.correct(
            CorrectExpenseCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                expense_id=recorded.expense_id,
                target_event_id=recorded.event.event_id,
                correlation_id=recorded.event.correlation_id,
                idempotency_key="expense-correct-vet",
                expected_stream_version=1,
                amount_minor=5000,
                currency="USD",
                category="Veterinary",
                payee="Reptile Vet",
                reference="INV-10-CORRECTED",
                reason="Invoice total was entered incorrectly.",
            )
        )

        current = projection.expense_for(bootstrap.household_id, recorded.expense_id)
        assert current is not None
        assert (current.amount_minor, current.currency, current.status) == (5000, "USD", "active")
        assert projection.total_active_minor(bootstrap.household_id, "USD") == 5000

        service.void(
            VoidExpenseCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                expense_id=recorded.expense_id,
                target_event_id=corrected.event.event_id,
                correlation_id=recorded.event.correlation_id,
                idempotency_key="expense-void-vet",
                expected_stream_version=2,
                reason="The vendor refunded this charge.",
            )
        )

        current = projection.expense_for(bootstrap.household_id, recorded.expense_id)
        assert current is not None and current.status == "voided"
        assert projection.total_active_minor(bootstrap.household_id, "USD") == 0
        events = store.load_stream(
            StreamKey(bootstrap.household_id, "expense", recorded.expense_id)
        )
        assert [event.event_type for event in events] == [
            "expense.recorded",
            "expense.corrected",
            "expense.voided",
        ]
        assert events[0].payload.amount_minor == 4500  # type: ignore[attr-defined]
        with engine.connect() as connection:
            audit_actions = (
                connection.execute(
                    text(
                        "SELECT action FROM security_audit WHERE household_id=:household_id "
                        "AND category='expense' ORDER BY recorded_at"
                    ),
                    {"household_id": str(bootstrap.household_id)},
                )
                .scalars()
                .all()
            )
        assert audit_actions == ["expense.recorded", "expense.corrected", "expense.voided"]
    finally:
        engine.dispose()


@pytest.mark.parametrize("role", ["owner", "administrator"])
def test_owner_and_administrator_can_manage_expenses(tmp_path: Path, role: str) -> None:
    engine, bootstrap, _store, service, _projection = _setup(tmp_path)
    try:
        result = service.record(
            RecordExpenseCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                role,
                uuid4(),
                f"expense-{role}",
                1200,
                "USD",
                "Supplies",
                None,
                None,
                None,
                datetime.now(UTC),
            )
        )
        assert result.current.amount_minor == 1200
    finally:
        engine.dispose()


@pytest.mark.parametrize("role", ["caretaker", "viewer"])
def test_caretaker_and_viewer_cannot_access_financial_commands(tmp_path: Path, role: str) -> None:
    engine, bootstrap, _store, service, _projection = _setup(tmp_path)
    try:
        with pytest.raises(ExpenseAuthorizationError, match=r"expense\.manage"):
            service.record(
                RecordExpenseCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    role,
                    uuid4(),
                    f"expense-forbidden-{role}",
                    1200,
                    "USD",
                    "Supplies",
                    None,
                    None,
                    None,
                    datetime.now(UTC),
                )
            )
    finally:
        engine.dispose()


def test_expense_correction_requires_reason_and_current_stream_version(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, _projection = _setup(tmp_path)
    try:
        recorded = service.record(
            RecordExpenseCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                uuid4(),
                "expense-reason-record",
                900,
                "USD",
                "Supplies",
                None,
                None,
                None,
                datetime.now(UTC),
            )
        )
        with pytest.raises(ExpenseValidationError, match="reason"):
            service.correct(
                CorrectExpenseCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    recorded.expense_id,
                    recorded.event.event_id,
                    recorded.event.correlation_id,
                    "expense-reason-missing",
                    1,
                    1000,
                    "USD",
                    "Supplies",
                    None,
                    None,
                    " ",
                )
            )
        with pytest.raises(ExpectedVersionConflictError):
            service.correct(
                CorrectExpenseCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    recorded.expense_id,
                    recorded.event.event_id,
                    recorded.event.correlation_id,
                    "expense-stale-version",
                    0,
                    1000,
                    "USD",
                    "Supplies",
                    None,
                    None,
                    "Corrected receipt.",
                )
            )
    finally:
        engine.dispose()


def test_expense_record_retry_returns_original_result(tmp_path: Path) -> None:
    engine, bootstrap, store, service, _projection = _setup(tmp_path)
    try:
        command_value = RecordExpenseCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            "owner",
            uuid4(),
            "expense-idempotent",
            1500,
            "USD",
            "Supplies",
            "Supplier",
            None,
            None,
            datetime(2026, 8, 3, tzinfo=UTC),
        )
        first = service.record(command_value)
        second = service.record(command_value)
        assert second.expense_id == first.expense_id
        assert (
            len(store.load_stream(StreamKey(bootstrap.household_id, "expense", first.expense_id)))
            == 1
        )
    finally:
        engine.dispose()


def test_expense_capabilities_are_financially_restricted() -> None:
    assert {"expense.view", "expense.manage"} <= ROLE_CAPABILITIES["owner"]
    assert {"expense.view", "expense.manage"} <= ROLE_CAPABILITIES["administrator"]
    assert "expense.view" not in ROLE_CAPABILITIES["caretaker"]
    assert "expense.view" not in ROLE_CAPABILITIES["viewer"]


def test_voided_expense_cannot_be_reinstated_or_changed(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, _projection = _setup(tmp_path)
    try:
        recorded = service.record(
            RecordExpenseCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                uuid4(),
                "expense-no-reinstate-record",
                800,
                "USD",
                "Supplies",
                None,
                None,
                None,
                datetime.now(UTC),
            )
        )
        voided = service.void(
            VoidExpenseCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                recorded.expense_id,
                recorded.event.event_id,
                recorded.event.correlation_id,
                "expense-no-reinstate-void",
                1,
                "Duplicate receipt.",
            )
        )
        with pytest.raises(ExpenseValidationError, match="cannot be changed or reinstated"):
            service.correct(
                CorrectExpenseCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    recorded.expense_id,
                    voided.event.event_id,
                    recorded.event.correlation_id,
                    "expense-no-reinstate-correct",
                    2,
                    900,
                    "USD",
                    "Supplies",
                    None,
                    None,
                    "Attempted change.",
                )
            )
        assert not hasattr(service, "reinstate")
    finally:
        engine.dispose()
