from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.application.inventory import (
    AdjustScaledStockCommand,
    ChangeInventoryPolicyCommand,
    CorrectStockCountCommand,
    CountStockCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveScaledStockCommand,
    ReceiveStockCommand,
    RegisterStructuredInventoryItemCommand,
    UseInventoryCommand,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.inventory.projections import (
    SQLAlchemyInventoryBalanceProjection,
)
from snaketracker.infrastructure.product_experience.projections import (
    ensure_product_projection_generations,
    product_projection_registry,
)
from snaketracker.infrastructure.purchases.projections import (
    SQLAlchemyInventoryAccountingProjection,
    SQLAlchemyInventoryCostProjection,
    SQLAlchemyInventoryEffectiveReceiptProjection,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.store import (
    ExpectedVersionConflictError,
    IdempotencyConflictError,
    StreamKey,
)
from snaketracker.worker.projections import ProjectionWorker

ROOT = Path(__file__).parents[2]


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "inventory-intelligence.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    owner = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"m65-b-inventory-intelligence-tests",
    ).bootstrap(
        BootstrapCommand(
            "Inventory Intelligence Home",
            "America/New_York",
            "owner@example.com",
            "Owner",
            "correct horse battery staple",
            "inventory-intelligence-bootstrap",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    balance = SQLAlchemyInventoryBalanceProjection(engine)
    accounting = SQLAlchemyInventoryAccountingProjection(
        balance, SQLAlchemyInventoryEffectiveReceiptProjection()
    )
    manager = ensure_product_projection_generations(engine)
    return engine, owner, store, InventoryService(store, accounting), manager


def _item(service: InventoryService, owner: object):  # type: ignore[no-untyped-def]
    return service.register_structured(
        RegisterStructuredInventoryItemCommand(
            owner.household_id,
            owner.user_id,
            uuid4(),
            "inventory-intelligence-item",
            "Medium rats",
            "food",
            "each",
            "whole_prey",
            "rat",
            "medium",
            "frozen_thawed",
            None,
            20_000,
        )
    )


def test_policy_use_count_and_count_correction_are_atomic_and_exact(tmp_path: Path) -> None:
    engine, owner, store, service, manager = _setup(tmp_path)
    try:
        item = _item(service, owner)
        policy = service.change_policy(
            ChangeInventoryPolicyCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "inventory-intelligence-policy",
                2,
                5_000,
                15_000,
                25_000,
                7,
                30,
            )
        )
        assert policy.balance.stream_version == 4
        assert (
            policy.balance.reorder_threshold_scaled,
            policy.balance.target_quantity_scaled,
            policy.balance.maximum_quantity_scaled,
            policy.balance.supplier_lead_time_days,
            policy.balance.recount_interval_days,
        ) == (5_000, 15_000, 25_000, 7, 30)
        now = datetime.now(UTC)

        first = service.count_stock(
            CountStockCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "inventory-intelligence-count",
                4,
                18_000,
                "full",
                uuid4(),
                "Freezer count",
                now,
            )
        )
        assert first.balance.on_hand_quantity_scaled == 18_000
        count = service.count_for_event(owner.household_id, item.item_id, first.event.event_id)
        assert count is not None
        assert (count.expected_quantity_scaled, count.actual_quantity_scaled) == (20_000, 18_000)
        assert count.variance_quantity_scaled == -2_000

        corrected = service.correct_count(
            CorrectStockCountCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "inventory-intelligence-count-correction",
                5,
                first.event.event_id,
                19_000,
                "Recounted the back row",
                datetime.now(UTC),
            )
        )
        assert corrected.balance.on_hand_quantity_scaled == 19_000
        assert corrected.balance.stream_version == 7
        counts = service.list_counts(owner.household_id, item_id=item.item_id)
        assert [(value.status, value.variance_quantity_scaled) for value in counts] == [
            ("active", -1_000),
            ("voided", -2_000),
        ]

        use_command = UseInventoryCommand(
            owner.household_id,
            owner.user_id,
            item.item_id,
            uuid4(),
            "inventory-intelligence-use",
            7,
            2_000,
            "maintenance",
            "Prepared two enclosures",
            datetime.now(UTC),
        )
        used = service.use_inventory(use_command)
        assert used.balance.on_hand_quantity_scaled == 17_000
        assert service.use_inventory(use_command).event.event_id == used.event.event_id
        with pytest.raises(IdempotencyConflictError):
            service.use_inventory(replace(use_command, quantity_scaled=3_000))
        with pytest.raises(ExpectedVersionConflictError):
            service.count_stock(
                CountStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "inventory-intelligence-stale-count",
                    7,
                    17_000,
                    "single",
                    uuid4(),
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError):
            service.use_inventory(
                UseInventoryCommand(
                    uuid4(),
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "cross-household-use",
                    8,
                    1_000,
                    "other",
                    None,
                    now,
                )
            )

        ProjectionWorker(engine, manager, product_projection_registry).run_once(limit=5000)
        costing = SQLAlchemyInventoryCostProjection(engine, manager).summary_for(
            owner.household_id, item.item_id
        )
        assert costing.unknown_remaining_quantity_scaled == 17_000
        events = store.load_stream(StreamKey(owner.household_id, "inventory-item", item.item_id))
        assert [event.event_type for event in events[-6:]] == [
            "inventory.reorder_policy_changed",
            "inventory.verification_policy_changed",
            "inventory.stock_counted",
            "event.voided",
            "inventory.stock_counted",
            "inventory.stock_consumed",
        ]
        assert events[-1].schema_version == 3

        replay_database = tmp_path / "inventory-intelligence-replay.sqlite3"
        replay_config = Config(ROOT / "alembic.ini")
        replay_config.set_main_option("script_location", str(ROOT / "migrations"))
        replay_config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{replay_database}")
        command.upgrade(replay_config, "head")
        replay_engine = create_sqlite_engine(replay_database, require_local_storage=False)
        try:
            replay_projection = SQLAlchemyInventoryBalanceProjection(replay_engine)
            with replay_engine.begin() as connection:
                replay_projection.apply(connection, events)
            replayed = replay_projection.balance_for(owner.household_id, item.item_id)
            assert replayed is not None
            assert replayed.on_hand_quantity_scaled == used.balance.on_hand_quantity_scaled
            assert replayed.stream_version == used.balance.stream_version
            assert [
                (value.status, value.variance_quantity_scaled)
                for value in replay_projection.list_counts(owner.household_id, item_id=item.item_id)
            ] == [("active", -1_000), ("voided", -2_000)]
        finally:
            replay_engine.dispose()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("minimum", "target", "maximum"),
    [(5_000, 4_000, None), (5_000, None, 4_000), (5_000, 8_000, 7_000)],
)
def test_policy_ordering_is_rejected_without_writing(
    tmp_path: Path, minimum: int, target: int | None, maximum: int | None
) -> None:
    engine, owner, store, service, _manager = _setup(tmp_path)
    try:
        item = _item(service, owner)
        with pytest.raises(InventoryValidationError):
            service.change_policy(
                ChangeInventoryPolicyCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "invalid-policy",
                    2,
                    minimum,
                    target,
                    maximum,
                    7,
                    30,
                )
            )
        assert (
            len(store.load_stream(StreamKey(owner.household_id, "inventory-item", item.item_id)))
            == 2
        )
    finally:
        engine.dispose()


def test_zero_variance_count_is_a_durable_verification(tmp_path: Path) -> None:
    engine, owner, _store, service, _manager = _setup(tmp_path)
    try:
        item = _item(service, owner)
        result = service.count_stock(
            CountStockCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "zero-variance-count",
                2,
                20_000,
                "cycle",
                uuid4(),
                None,
                datetime.now(UTC),
            )
        )
        assert result.balance.on_hand_quantity_scaled == 20_000
        assert result.balance.last_count_expected_scaled == 20_000
        assert result.balance.last_count_actual_scaled == 20_000
        assert (
            service.list_counts(owner.household_id, item_id=item.item_id)[
                0
            ].variance_quantity_scaled
            == 0
        )
    finally:
        engine.dispose()


def test_inventory_intelligence_rejects_invalid_policy_use_and_count_boundaries(
    tmp_path: Path,
) -> None:
    engine, owner, _store, service, _manager = _setup(tmp_path)
    try:
        item = _item(service, owner)
        now = datetime.now(UTC)
        naive = now.replace(tzinfo=None)

        with pytest.raises(InventoryValidationError, match="must be positive"):
            service.use_inventory(
                UseInventoryCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "zero-use",
                    2,
                    0,
                    "care",
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="valid inventory use"):
            service.use_inventory(
                UseInventoryCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "invalid-use-kind",
                    2,
                    1_000,
                    "feeding",
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="receipt time"):
            service.receive_scaled(
                ReceiveScaledStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "naive-receipt-time",
                    2,
                    1_000,
                    None,
                    naive,
                )
            )
        with pytest.raises(InventoryValidationError, match="cannot be zero"):
            service.adjust_scaled(
                AdjustScaledStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "zero-adjustment",
                    2,
                    0,
                    "No variance",
                )
            )
        with pytest.raises(InventoryValidationError, match="controlled quantity"):
            service.receive(
                ReceiveStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "legacy-receipt-on-structured-item",
                    2,
                    1,
                    None,
                )
            )
        with pytest.raises(InventoryValidationError, match="status filter"):
            service.list_balances(owner.household_id, status="deleted")
        with pytest.raises(InventoryValidationError, match="include a timezone"):
            service.use_inventory(
                UseInventoryCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "naive-use-time",
                    2,
                    1_000,
                    "care",
                    None,
                    naive,
                )
            )
        with pytest.raises(InventoryValidationError, match="cannot be negative"):
            service.change_policy(
                ChangeInventoryPolicyCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "negative-policy",
                    2,
                    -1_000,
                    None,
                    None,
                    None,
                    None,
                )
            )
        with pytest.raises(InventoryValidationError, match="between 1 and 3650"):
            service.change_policy(
                ChangeInventoryPolicyCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "invalid-policy-days",
                    2,
                    0,
                    0,
                    0,
                    0,
                    None,
                )
            )
        with pytest.raises(InventoryValidationError, match="cannot be negative"):
            service.count_stock(
                CountStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "negative-count",
                    2,
                    -1_000,
                    "single",
                    uuid4(),
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="context is invalid"):
            service.count_stock(
                CountStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "invalid-count-context",
                    2,
                    0,
                    "warehouse",
                    uuid4(),
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="include a timezone"):
            service.count_stock(
                CountStockCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "naive-count-time",
                    2,
                    0,
                    "single",
                    uuid4(),
                    None,
                    naive,
                )
            )

        count = service.count_stock(
            CountStockCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "zero-stock-count",
                2,
                0,
                "single",
                uuid4(),
                None,
                now,
            )
        )
        with pytest.raises(InventoryValidationError, match="missing or already corrected"):
            service.correct_count(
                CorrectStockCountCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "missing-count-correction",
                    3,
                    uuid4(),
                    0,
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="cannot be negative"):
            service.correct_count(
                CorrectStockCountCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "negative-count-correction",
                    3,
                    count.event.event_id,
                    -1_000,
                    None,
                    now,
                )
            )
        with pytest.raises(InventoryValidationError, match="include a timezone"):
            service.correct_count(
                CorrectStockCountCommand(
                    owner.household_id,
                    owner.user_id,
                    item.item_id,
                    uuid4(),
                    "naive-count-correction",
                    3,
                    count.event.event_id,
                    0,
                    None,
                    naive,
                )
            )
        corrected = service.correct_count(
            CorrectStockCountCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "zero-count-correction",
                3,
                count.event.event_id,
                0,
                None,
                now,
            )
        )
        assert corrected.balance.on_hand_quantity_scaled == 0
    finally:
        engine.dispose()


def test_migration_refuses_to_drop_durable_inventory_intelligence_history(
    tmp_path: Path,
) -> None:
    engine, owner, _store, service, _manager = _setup(tmp_path)
    try:
        item = _item(service, owner)
        service.count_stock(
            CountStockCommand(
                owner.household_id,
                owner.user_id,
                item.item_id,
                uuid4(),
                "guarded-count",
                2,
                20_000,
                "single",
                uuid4(),
                None,
                datetime.now(UTC),
            )
        )
    finally:
        engine.dispose()

    database = tmp_path / "inventory-intelligence.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    with pytest.raises(RuntimeError, match="downgrade blocked"):
        command.downgrade(config, "0016_inventory_acquisition")
