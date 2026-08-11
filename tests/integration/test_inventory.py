from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.animals import (
    AnimalService,
    CorrectFeedingCommand,
    RecordFeedingCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.inventory import (
    AdjustStockCommand,
    ChangeReorderPolicyCommand,
    ConsumeStockCommand,
    ExpireStockCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveStockCommand,
    RegisterInventoryItemCommand,
    ReserveStockCommand,
    ReverseConsumptionCommand,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
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


def test_inventory_reservation_is_consumed_deterministically_and_policy_changes(
    tmp_path: Path,
) -> None:
    engine, bootstrap, _store, service, projection = _setup(tmp_path)
    try:
        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-reservation-item",
                "Frozen mice",
                "item",
                2,
            )
        )
        service.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-reservation-receive",
                1,
                10,
                None,
            )
        )
        service.reserve(
            ReserveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-reserve",
                2,
                3,
                "feeding-plan-1",
            )
        )
        consumed = service.consume(
            ConsumeStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-consume-reserved",
                3,
                2,
                None,
            )
        )
        service.reverse_consumption(
            ReverseConsumptionCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-reverse-reserved",
                4,
                consumed.event.event_id,
                2,
                "Reserved feeding was cancelled.",
            )
        )
        service.change_reorder_policy(
            ChangeReorderPolicyCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "inventory-reorder-policy",
                5,
                5,
            )
        )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None
        assert (balance.on_hand_quantity, balance.reserved_quantity) == (10, 3)
        assert balance.reorder_threshold == 5
        assert balance.stream_version == 6
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


def test_stock_linked_feeding_void_and_reinstatement_compensate_atomically(tmp_path: Path) -> None:
    engine, bootstrap, store, inventory, projection = _setup(tmp_path)
    try:
        item = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "linked-register-stock",
                "Medium rats",
                "item",
                None,
            )
        )
        inventory.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "linked-receive-stock",
                1,
                5,
                None,
            )
        )
        animals = AnimalService(
            store,
            SQLAlchemyAnimalCurrentProjection(engine),
            inventory_projection=projection,
        )
        animal = animals.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "linked-register-animal",
                "Nyx",
                "Python regius",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        feeding = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "linked-feeding",
                datetime(2026, 8, 10, 12, tzinfo=UTC),
                "rat",
                "medium",
                None,
                "frozen_thawed",
                1,
                "accepted",
                None,
                inventory_item_id=item.item_id,
                inventory_expected_stream_version=2,
                inventory_quantity=2,
            )
        )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 3

        animals.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "linked-feeding-void",
                "Entered against the wrong animal.",
            )
        )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 5

        animals.reinstate_event(
            ReinstateAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "linked-feeding-reinstate",
                "The original animal was correct.",
            )
        )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 3
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "inventory-item", item.item_id)
            )
        ] == [
            "inventory.item_registered",
            "inventory.stock_received",
            "inventory.stock_consumed",
            "inventory.consumption_reversed",
            "inventory.stock_consumed",
        ]
    finally:
        engine.dispose()


def test_stock_linked_feeding_rolls_back_when_inventory_is_insufficient(tmp_path: Path) -> None:
    engine, bootstrap, store, inventory, projection = _setup(tmp_path)
    try:
        item = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "rollback-register-stock",
                "Large rats",
                "item",
                None,
            )
        )
        animals = AnimalService(
            store,
            SQLAlchemyAnimalCurrentProjection(engine),
            inventory_projection=projection,
        )
        animal = animals.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "rollback-register-animal",
                "Sol",
                "Boa imperator",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )

        with pytest.raises(InventoryValidationError, match="Insufficient available inventory"):
            animals.record_feeding(
                RecordFeedingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal.animal_id,
                    uuid4(),
                    "rollback-linked-feeding",
                    datetime(2026, 8, 10, 12, tzinfo=UTC),
                    "rat",
                    "large",
                    None,
                    "frozen_thawed",
                    1,
                    "accepted",
                    None,
                    inventory_item_id=item.item_id,
                    inventory_expected_stream_version=1,
                    inventory_quantity=1,
                )
            )

        animal_events = store.load_stream(
            StreamKey(bootstrap.household_id, "animal", animal.animal_id)
        )
        assert [event.event_type for event in animal_events] == ["animal.registered"]
    finally:
        engine.dispose()


def test_stock_linked_feeding_correction_replaces_consumption_atomically(tmp_path: Path) -> None:
    engine, bootstrap, store, inventory, projection = _setup(tmp_path)
    try:
        item = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "correct-register-stock",
                "Rat pups",
                "item",
                None,
            )
        )
        inventory.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                item.item_id,
                uuid4(),
                "correct-receive-stock",
                1,
                5,
                None,
            )
        )
        animals = AnimalService(
            store,
            SQLAlchemyAnimalCurrentProjection(engine),
            inventory_projection=projection,
        )
        animal = animals.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "correct-register-animal",
                "Luna",
                "Python regius",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        feeding = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "correct-linked-feeding",
                datetime(2026, 8, 10, 12, tzinfo=UTC),
                "rat",
                "pup",
                None,
                "frozen_thawed",
                2,
                "accepted",
                None,
                inventory_item_id=item.item_id,
                inventory_expected_stream_version=2,
                inventory_quantity=2,
            )
        )

        correction = animals.correct_feeding(
            CorrectFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "correct-linked-feeding-replacement",
                datetime(2026, 8, 10, 13, tzinfo=UTC),
                "rat",
                "pup",
                None,
                "frozen_thawed",
                1,
                "accepted",
                "Corrected quantity.",
                inventory_quantity=1,
            )
        )

        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None and balance.on_hand_quantity == 4
        link = projection.consumption_for_source(bootstrap.household_id, correction.event.event_id)
        assert link is not None and (link.quantity, link.status) == (1, "active")
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "inventory-item", item.item_id)
            )
        ][-2:] == ["inventory.consumption_reversed", "inventory.stock_consumed"]
    finally:
        engine.dispose()


def test_inventory_rejects_invalid_commands_without_changing_balance(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, projection = _setup(tmp_path)
    try:
        with pytest.raises(InventoryValidationError, match="Reorder threshold"):
            service.register(
                RegisterInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "invalid-threshold",
                    "Mice",
                    "item",
                    -1,
                )
            )
        with pytest.raises(InventoryValidationError, match="Inventory name"):
            service.register(
                RegisterInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "invalid-name",
                    " ",
                    "item",
                    None,
                )
            )

        item = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "validation-item",
                "Mice",
                "item",
                None,
            )
        )
        base = (
            bootstrap.household_id,
            bootstrap.user_id,
            item.item_id,
            uuid4(),
        )
        with pytest.raises(InventoryValidationError, match="stream version"):
            service.receive(ReceiveStockCommand(*base, "invalid-version", 0, 1, None))
        with pytest.raises(InventoryValidationError, match="positive"):
            service.receive(ReceiveStockCommand(*base, "invalid-quantity", 1, 0, None))
        with pytest.raises(InventoryValidationError, match="too long"):
            service.receive(ReceiveStockCommand(*base, "long-reference", 1, 1, "x" * 501))
        with pytest.raises(InventoryValidationError, match="Reservation key"):
            service.reserve(ReserveStockCommand(*base, "invalid-reservation", 1, 1, " "))
        with pytest.raises(InventoryValidationError, match="cannot be zero"):
            service.adjust(AdjustStockCommand(*base, "zero-adjustment", 1, 0, "Counted"))
        with pytest.raises(InventoryValidationError, match="positive"):
            service.expire(ExpireStockCommand(*base, "zero-expiry", 1, 0, "Expired"))
        with pytest.raises(InventoryValidationError, match="Reorder threshold"):
            service.change_reorder_policy(
                ChangeReorderPolicyCommand(*base, "invalid-policy", 1, -1)
            )
        with pytest.raises(InventoryValidationError, match="does not exist"):
            service.consume(
                ConsumeStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    uuid4(),
                    "missing-item",
                    1,
                    1,
                    None,
                )
            )

        service.receive(ReceiveStockCommand(*base, "valid-receipt", 1, 5, None))
        service.reserve(ReserveStockCommand(*base, "valid-reservation", 2, 4, "feeding-plan"))
        with pytest.raises(InventoryValidationError, match="available inventory to reserve"):
            service.reserve(ReserveStockCommand(*base, "over-reservation", 3, 2, "second-plan"))
        with pytest.raises(InventoryValidationError, match="conflicts with reservations"):
            service.adjust(
                AdjustStockCommand(*base, "reserved-adjustment", 3, -2, "Physical count")
            )
        with pytest.raises(InventoryValidationError, match="available inventory to expire"):
            service.expire(ExpireStockCommand(*base, "reserved-expiry", 3, 2, "Expired"))

        consumed = service.consume(ConsumeStockCommand(*base, "valid-consumption", 3, 2, None))
        with pytest.raises(InventoryValidationError, match="target is invalid"):
            service.reverse_consumption(
                ReverseConsumptionCommand(*base, "missing-target", 4, uuid4(), 2, "Correction")
            )
        with pytest.raises(InventoryValidationError, match="consumed quantity"):
            service.reverse_consumption(
                ReverseConsumptionCommand(
                    *base,
                    "wrong-quantity",
                    4,
                    consumed.event.event_id,
                    1,
                    "Correction",
                )
            )
        service.reverse_consumption(
            ReverseConsumptionCommand(
                *base,
                "valid-reversal",
                4,
                consumed.event.event_id,
                2,
                "Correction",
            )
        )
        with pytest.raises(InventoryValidationError, match="already been reversed"):
            service.reverse_consumption(
                ReverseConsumptionCommand(
                    *base,
                    "duplicate-reversal",
                    5,
                    consumed.event.event_id,
                    2,
                    "Correction",
                )
            )
        balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert balance is not None
        assert (balance.on_hand_quantity, balance.reserved_quantity, balance.stream_version) == (
            5,
            4,
            5,
        )
    finally:
        engine.dispose()
