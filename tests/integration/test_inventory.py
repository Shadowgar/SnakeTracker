from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.inventory import (
    AdjustStockCommand,
    ConsumeStockCommand,
    ExpireStockCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveStockCommand,
    RegisterInventoryItemCommand,
    ReverseConsumptionCommand,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.inventory.projections import SQLAlchemyInventoryBalanceProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.store import (
    ExpectedVersionConflictError,
    IdempotencyConflictError,
    StreamKey,
)

ROOT = Path(__file__).parents[2]
SECRET = b"phase5-inventory-test-secret-32-bytes"


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "inventory.sqlite3"
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
            household_name="Inventory Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="phase5-inventory-bootstrap",
            correlation_id=uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    projection = SQLAlchemyInventoryBalanceProjection(engine)
    return engine, bootstrap, store, InventoryService(store, projection), projection


def test_inventory_balance_follows_receipt_consumption_compensation_and_adjustment(
    tmp_path: Path,
) -> None:
    engine, bootstrap, store, service, projection = _setup(tmp_path)
    try:
        registered = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-register-rats",
                "Medium rats",
                "item",
                4,
            )
        )
        received = service.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-receive-rats",
                1,
                10,
                "Order 1001",
            )
        )
        consumed = service.consume(
            ConsumeStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-consume-rats",
                2,
                4,
                None,
            )
        )
        service.reverse_consumption(
            ReverseConsumptionCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-reverse-rats",
                3,
                consumed.event.event_id,
                4,
                "Feeding was voided.",
            )
        )
        service.adjust(
            AdjustStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-adjust-rats",
                4,
                -3,
                "Physical count reconciliation.",
            )
        )
        service.expire(
            ExpireStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-expire-rats",
                5,
                2,
                "Past safe-use date.",
            )
        )

        balance = projection.balance_for(bootstrap.household_id, registered.item_id)
        assert balance is not None
        assert (balance.on_hand_quantity, balance.consumed_quantity, balance.expired_quantity) == (
            5,
            0,
            2,
        )
        assert balance.stream_version == 6
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "inventory-item", registered.item_id)
            )
        ] == [
            "inventory.item_registered",
            "inventory.stock_received",
            "inventory.stock_consumed",
            "inventory.consumption_reversed",
            "inventory.stock_adjusted",
            "inventory.stock_expired",
        ]
        assert received.event.stream_version == 2
    finally:
        engine.dispose()


def test_inventory_invariant_failure_rolls_back_event_and_projection(tmp_path: Path) -> None:
    engine, bootstrap, store, service, projection = _setup(tmp_path)
    try:
        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-register-mice",
                "Fuzzy mice",
                "item",
                None,
            )
        )
        service.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-receive-mice",
                1,
                2,
                None,
            )
        )

        with pytest.raises(InventoryValidationError, match="Insufficient available inventory"):
            service.consume(
                ConsumeStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    item.item_id,
                    uuid4(),
                    "inventory-overconsume-mice",
                    2,
                    3,
                    None,
                )
            )

        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 2
        assert (
            len(
                store.load_stream(StreamKey(bootstrap.household_id, "inventory-item", item.item_id))
            )
            == 2
        )
    finally:
        engine.dispose()


def test_inventory_expected_version_and_idempotent_retry_are_explicit(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, projection = _setup(tmp_path)
    try:
        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-register-chicks",
                "Day-old chicks",
                "item",
                None,
            )
        )
        command_value = ReceiveStockCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            item.item_id,
            uuid4(),
            "inventory-receive-chicks",
            1,
            5,
            None,
        )
        first = service.receive(command_value)
        retry = service.receive(command_value)
        assert retry.event.event_id == first.event.event_id

        with pytest.raises(ExpectedVersionConflictError):
            service.receive(
                ReceiveStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    item.item_id,
                    uuid4(),
                    "inventory-stale-chicks",
                    1,
                    1,
                    None,
                )
            )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 5
    finally:
        engine.dispose()


def test_inventory_concurrent_writers_commit_one_expected_version_winner(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, projection = _setup(tmp_path)
    try:
        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-register-concurrent",
                "Small rats",
                "item",
                None,
            )
        )
        barrier = Barrier(2)

        def receive(key: str) -> str:
            barrier.wait()
            try:
                service.receive(
                    ReceiveStockCommand(
                        bootstrap.household_id,
                        bootstrap.user_id,
                        item.item_id,
                        uuid4(),
                        key,
                        1,
                        1,
                        None,
                    )
                )
            except ExpectedVersionConflictError:
                return "conflict"
            return "committed"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = sorted(executor.map(receive, ("concurrent-a", "concurrent-b")))

        assert outcomes == ["committed", "conflict"]
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None
        assert (balance.on_hand_quantity, balance.stream_version) == (1, 2)
    finally:
        engine.dispose()


def test_inventory_idempotency_key_rejects_different_command_hash(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, _projection = _setup(tmp_path)
    try:
        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-register-idempotency",
                "Hopper mice",
                "item",
                None,
            )
        )
        first = ReceiveStockCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            item.item_id,
            uuid4(),
            "inventory-hash-key",
            1,
            2,
            None,
        )
        service.receive(first)

        with pytest.raises(IdempotencyConflictError):
            service.receive(
                ReceiveStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    item.item_id,
                    first.correlation_id,
                    first.idempotency_key,
                    1,
                    3,
                    None,
                )
            )
    finally:
        engine.dispose()
