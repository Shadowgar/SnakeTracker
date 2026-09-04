from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    CorrectFeedingCommand,
    RecordFeedingCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.inventory import (
    AdjustStockCommand,
    ArchiveInventoryItemCommand,
    ChangeReorderPolicyCommand,
    ConsumeStockCommand,
    ExpireStockCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveStockCommand,
    RegisterInventoryItemCommand,
    ReserveStockCommand,
    RestoreInventoryItemCommand,
    ReverseConsumptionCommand,
    UpdateInventoryItemCommand,
)
from snaketracker.domains.inventory.contracts import InventoryConsumptionReversedV1
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
    canonical_command_hash,
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


def test_inventory_item_edit_archive_restore_preserves_stock_history(tmp_path: Path) -> None:
    engine, bootstrap, store, service, _projection = _setup(tmp_path)
    try:
        registered = service.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "inventory-lifecycle-register",
                "Small mice",
                "item",
                2,
            )
        )
        service.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-lifecycle-receive",
                1,
                8,
                "Order 2002",
            )
        )
        updated = service.update_item(
            UpdateInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-lifecycle-edit",
                2,
                "Small thawed mice",
                "prey",
                3,
            )
        )
        assert updated.balance.name == "Small thawed mice"
        assert updated.balance.on_hand_quantity == 8
        archived = service.archive_item(
            ArchiveInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-lifecycle-archive",
                3,
                "Supplier changed.",
            )
        )
        assert archived.balance.status == "archived"
        assert service.list_balances(bootstrap.household_id) == ()
        assert service.list_balances(bootstrap.household_id, status="archived") == (
            archived.balance,
        )
        with pytest.raises(InventoryValidationError, match="Only active"):
            service.adjust(
                AdjustStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    registered.item_id,
                    uuid4(),
                    "inventory-lifecycle-archived-adjust",
                    4,
                    1,
                    "Must fail.",
                )
            )

        restored = service.restore_item(
            RestoreInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                registered.item_id,
                uuid4(),
                "inventory-lifecycle-restore",
                4,
                "Supplier returned.",
            )
        )
        assert restored.balance.status == "active"
        assert restored.balance.on_hand_quantity == 8
        assert service.list_balances(bootstrap.household_id) == (restored.balance,)
        assert not hasattr(service, "delete_item")
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "inventory-item", registered.item_id)
            )
        ] == [
            "inventory.item_registered",
            "inventory.stock_received",
            "inventory.item_updated",
            "inventory.item_archived",
            "inventory.item_restored",
        ]
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
        consumed_balance = projection.balance_for(bootstrap.household_id, item.item_id)
        assert consumed_balance is not None
        assert (consumed_balance.on_hand_quantity, consumed_balance.reserved_quantity) == (8, 1)
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
                "Charlotte",
                "Grammostola pulchra",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                animal_type="spider",
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

        with pytest.raises(AnimalValidationError, match="replacement quantity must be positive"):
            animals.correct_feeding(
                CorrectFeedingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    animal.animal_id,
                    feeding.event.event_id,
                    "correct-linked-feeding-zero-replacement",
                    datetime(2026, 8, 10, 13, tzinfo=UTC),
                    "rat",
                    "pup",
                    None,
                    "frozen_thawed",
                    1,
                    "accepted",
                    "Invalid zero replacement.",
                    inventory_quantity=0,
                )
            )

        animals.correct_feeding(
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
        link = projection.consumption_for_source(bootstrap.household_id, feeding.event.event_id)
        assert link is not None and (link.quantity, link.status) == (1, "active")
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "inventory-item", item.item_id)
            )
        ][-2:] == ["inventory.consumption_reversed", "inventory.stock_consumed"]

        animals.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "correct-linked-feeding-void-original",
                "Corrected feeding was voided.",
            )
        )
        compensated = projection.balance_for(bootstrap.household_id, item.item_id)
        assert compensated is not None and compensated.on_hand_quantity == 5
        compensated_link = projection.consumption_for_source(
            bootstrap.household_id, feeding.event.event_id
        )
        assert compensated_link is not None and compensated_link.status == "reversed"

        unlinked = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "legacy-hash-feeding",
                datetime(2026, 8, 11, 12, tzinfo=UTC),
                "mouse",
                "small",
                None,
                "frozen_thawed",
                1,
                "accepted",
                None,
            )
        )
        legacy_command = CorrectFeedingCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            "owner",
            animal.animal_id,
            unlinked.event.event_id,
            "legacy-hash-feeding-correction",
            datetime(2026, 8, 11, 13, tzinfo=UTC),
            "mouse",
            "small",
            None,
            "frozen_thawed",
            1,
            "accepted",
            "Corrected time.",
        )
        legacy_result = animals.correct_feeding(legacy_command)
        legacy_hash = canonical_command_hash(
            {
                "target_event_id": str(unlinked.event.event_id),
                "occurred_at": legacy_command.occurred_at.isoformat(),
                "prey_type": "mouse",
                "prey_size": "small",
                "prey_weight_grams": None,
                "preparation_method": "frozen_thawed",
                "quantity": 1,
                "outcome": "accepted",
                "notes": "Corrected time.",
            }
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE idempotency_operations SET command_hash=:command_hash "
                    "WHERE household_id=:household_id AND actor_user_id=:actor_user_id "
                    "AND operation_scope='animals.correct.animal.feeding_recorded' "
                    "AND idempotency_key=:idempotency_key"
                ),
                {
                    "command_hash": legacy_hash,
                    "household_id": str(bootstrap.household_id),
                    "actor_user_id": str(bootstrap.user_id),
                    "idempotency_key": legacy_command.idempotency_key,
                },
            )
        replayed = animals.correct_feeding(legacy_command)
        assert replayed.event.event_id == legacy_result.event.event_id
    finally:
        engine.dispose()


def test_inventory_projection_rejects_cross_item_reversal_allocation(tmp_path: Path) -> None:
    engine, bootstrap, _store, service, projection = _setup(tmp_path)
    try:
        consumed_events = []
        for index, name in enumerate(("Mice", "Crickets"), start=1):
            item = service.register(
                RegisterInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    f"cross-item-register-{index}",
                    name,
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
                    f"cross-item-receive-{index}",
                    1,
                    10,
                    None,
                )
            )
            consumed = service.consume(
                ConsumeStockCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    item.item_id,
                    uuid4(),
                    f"cross-item-consume-{index}",
                    2,
                    2,
                    None,
                )
            )
            consumed_events.append(consumed.event)

        wrong_stream_reversal = replace(
            consumed_events[1],
            event_id=uuid4(),
            stream_version=4,
            event_type="inventory.consumption_reversed",
            payload=InventoryConsumptionReversedV1(
                consumed_events[0].event_id,
                2,
                "Cross-item reversal must fail.",
            ),
        )
        with (
            engine.begin() as connection,
            pytest.raises(InventoryValidationError, match="missing or inconsistent"),
        ):
            projection.apply(connection, (wrong_stream_reversal,))
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
        with pytest.raises(InventoryValidationError, match="Inventory name is too long"):
            service.register(
                RegisterInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "long-name",
                    "x" * 201,
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
