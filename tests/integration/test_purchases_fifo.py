from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    DeleteAnimalCareRecordCommand,
    RecordInventoryFeedingCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationService,
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.application.inventory import (
    AdjustScaledStockCommand,
    ArchiveInventoryItemCommand,
    ConsumeScaledStockCommand,
    ExpireStockCommand,
    InventoryService,
    InventoryValidationError,
    RegisterInventoryItemCommand,
    RegisterStructuredInventoryItemCommand,
)
from snaketracker.application.purchases import (
    AcquireNewInventoryCommand,
    AssignExistingStockCostCommand,
    ControlPurchaseCommand,
    CorrectPurchaseCommand,
    CorrectPurchaseLineCommand,
    CurrencyValue,
    PostPurchaseCommand,
    PurchaseAuthorizationError,
    PurchaseLineCommand,
    PurchaseService,
    PurchaseValidationError,
    _currency,
    _nonnegative_money,
    _optional_text,
    _positive_money,
    _quantity,
    _required_text,
    _resize_assignment_portions,
    _utc,
    allocate_acquisition_costs,
)
from snaketracker.domains.inventory.contracts import (
    InventoryCostAssignmentPortionV1,
    InventoryReceiptCorrectedV1,
)
from snaketracker.domains.purchases.contracts import (
    PurchaseCorrectedV1,
    PurchaseLineV1,
    PurchaseRecordedV2,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.inventory.projections import SQLAlchemyInventoryBalanceProjection
from snaketracker.infrastructure.product_experience.projections import (
    ensure_product_projection_generations,
    product_projection_registry,
)
from snaketracker.infrastructure.purchases.projections import (
    SQLAlchemyInventoryAccountingProjection,
    SQLAlchemyInventoryCostProjection,
    SQLAlchemyInventoryEffectiveReceiptProjection,
    SQLAlchemyPurchaseCurrentProjection,
    _acquisition_mode,
    _as_int,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.control_contracts import EventVoidedV1
from snaketracker.platform.events.store import StreamKey
from snaketracker.worker.projections import ProjectionWorker

ROOT = Path(__file__).parents[2]


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "purchases.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    owner = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"m65-a2-purchase-secret-for-tests-only",
    ).bootstrap(
        BootstrapCommand(
            "Purchase Home",
            "UTC",
            "owner@example.com",
            "Owner",
            "correct horse battery staple",
            "purchase-bootstrap",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    manager = ensure_product_projection_generations(engine)
    balance = SQLAlchemyInventoryBalanceProjection(engine)
    costing = SQLAlchemyInventoryCostProjection(engine, manager)
    accounting = SQLAlchemyInventoryAccountingProjection(
        balance, SQLAlchemyInventoryEffectiveReceiptProjection()
    )
    inventory = InventoryService(store, accounting)
    purchases = PurchaseService(
        store,
        accounting,
        SQLAlchemyPurchaseCurrentProjection(engine),
        costing,
    )
    return engine, owner, store, inventory, purchases, manager


def _catch_up(engine, manager) -> None:  # type: ignore[no-untyped-def]
    ProjectionWorker(engine, manager, product_projection_registry).run_once(limit=5000)


def _cash_facts_table(manager) -> str:  # type: ignore[no-untyped-def]
    return manager.active_layout("cash_spend").component("cash_spend_facts", "facts")


def _item(inventory: InventoryService, owner, name: str, key: str):  # type: ignore[no-untyped-def]
    return inventory.register_structured(
        RegisterStructuredInventoryItemCommand(
            household_id=owner.household_id,
            actor_user_id=owner.user_id,
            correlation_id=uuid4(),
            idempotency_key=key,
            name=name,
            inventory_type="food",
            unit_code="each",
            food_category="whole_prey",
            food_type="mouse",
            size_stage="small",
            preparation_method="frozen_thawed",
            reorder_threshold_scaled=None,
            starting_quantity_scaled=0,
        )
    )


def _post(
    purchases: PurchaseService,
    owner,  # type: ignore[no-untyped-def]
    *,
    key: str,
    lines: tuple[PurchaseLineCommand, ...],
    total: int,
    tax: int = 0,
    fee: int = 0,
    discount: int = 0,
    occurred_at: datetime | None = None,
    currency: str = "USD",
):
    return purchases.post(
        PostPurchaseCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            uuid4(),
            key,
            "Reptile Supply",
            currency,
            "Receipt 42",
            "A2 purchase fixture",
            occurred_at or datetime(2026, 9, 10, 12, tzinfo=UTC),
            tax,
            fee,
            discount,
            total,
            lines,
        )
    )


def test_unified_new_inventory_tracks_paid_or_untracked_stock_and_consumption(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        paid = purchases.acquire_new(
            AcquireNewInventoryCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                uuid4(),
                "unified-paid-item",
                "Small Frozen Rat",
                "food",
                "each",
                "whole_prey",
                "rat",
                "small",
                "frozen_thawed",
                5_000,
                20_000,
                4_000,
                "USD",
                "Rat Supplier",
                "Receipt unified",
                datetime(2026, 9, 11, 12, tzinfo=UTC),
            )
        )
        assert paid.purchase_id is not None
        assert (
            purchases.acquire_new(
                replace(
                    AcquireNewInventoryCommand(
                        owner.household_id,
                        owner.user_id,
                        "owner",
                        uuid4(),
                        "unified-paid-item",
                        "Small Frozen Rat",
                        "food",
                        "each",
                        "whole_prey",
                        "rat",
                        "small",
                        "frozen_thawed",
                        5_000,
                        20_000,
                        4_000,
                        "USD",
                        "Rat Supplier",
                        "Receipt unified",
                        datetime(2026, 9, 11, 12, tzinfo=UTC),
                    ),
                    correlation_id=uuid4(),
                )
            )
            == paid
        )
        paid_balance = inventory.balance_for(owner.household_id, paid.item_id)
        assert paid_balance is not None and paid_balance.on_hand_quantity_scaled == 20_000
        _catch_up(engine, manager)
        paid_summary = purchases.cost_summary_for(owner.household_id, paid.item_id)
        assert paid_summary.known_remaining == (CurrencyValue("USD", 4_000),)
        assert paid_summary.unknown_remaining_quantity_scaled == 0

        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                paid.item_id,
                uuid4(),
                "unified-feed-one",
                2,
                1_000,
                None,
            )
        )
        _catch_up(engine, manager)
        consumed = purchases.cost_summary_for(owner.household_id, paid.item_id)
        assert consumed.known_remaining == (CurrencyValue("USD", 3_800),)
        assert consumed.known_consumed == (CurrencyValue("USD", 200),)

        untracked = purchases.acquire_new(
            AcquireNewInventoryCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                uuid4(),
                "unified-untracked-item",
                "Cost Not Tracked Rat",
                "food",
                "each",
                "whole_prey",
                "rat",
                "small",
                "frozen_thawed",
                None,
                5_000,
                0,
                "USD",
                None,
                None,
                datetime(2026, 9, 11, 13, tzinfo=UTC),
            )
        )
        assert untracked.purchase_id is None
        assert (
            purchases.acquire_new(
                replace(
                    AcquireNewInventoryCommand(
                        owner.household_id,
                        owner.user_id,
                        "owner",
                        uuid4(),
                        "unified-untracked-item",
                        "Cost Not Tracked Rat",
                        "food",
                        "each",
                        "whole_prey",
                        "rat",
                        "small",
                        "frozen_thawed",
                        None,
                        5_000,
                        0,
                        "USD",
                        None,
                        None,
                        datetime(2026, 9, 11, 13, tzinfo=UTC),
                    ),
                    correlation_id=uuid4(),
                )
            )
            == untracked
        )
        _catch_up(engine, manager)
        untracked_summary = purchases.cost_summary_for(owner.household_id, untracked.item_id)
        assert untracked_summary.known_remaining == ()
        assert untracked_summary.unknown_remaining_quantity_scaled == 5_000
        assert len(purchases.list_purchases(owner.household_id)) == 1
    finally:
        engine.dispose()


def test_existing_stock_cost_assignment_is_partial_bounded_and_quantity_neutral(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        legacy = inventory.register_structured(
            RegisterStructuredInventoryItemCommand(
                owner.household_id,
                owner.user_id,
                uuid4(),
                "legacy-cost-item",
                "Legacy Frozen Rat",
                "food",
                "each",
                "whole_prey",
                "rat",
                "small",
                "frozen_thawed",
                None,
                30_000,
            )
        )
        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                legacy.item_id,
                uuid4(),
                "legacy-consumed-ten",
                2,
                10_000,
                None,
            )
        )
        _catch_up(engine, manager)
        assert (
            purchases.cost_summary_for(
                owner.household_id, legacy.item_id
            ).unknown_remaining_quantity_scaled
            == 20_000
        )

        command = AssignExistingStockCostCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            uuid4(),
            "assign-partial-legacy-cost",
            legacy.item_id,
            3,
            10_000,
            1_800,
            "USD",
            "Remembered Supplier",
            "Historical receipt",
            datetime(2026, 8, 1, 12, tzinfo=UTC),
        )
        assigned = purchases.assign_existing_stock_cost(command)
        assert purchases.assign_existing_stock_cost(command).purchase_id == assigned.purchase_id
        balance = inventory.balance_for(owner.household_id, legacy.item_id)
        assert balance is not None
        assert balance.on_hand_quantity_scaled == 20_000
        assert balance.stream_version == 4
        _catch_up(engine, manager)
        summary = purchases.cost_summary_for(owner.household_id, legacy.item_id)
        assert summary.known_remaining == (CurrencyValue("USD", 1_800),)
        assert summary.known_consumed == ()
        assert summary.unknown_remaining_quantity_scaled == 10_000

        with pytest.raises(PurchaseValidationError, match="10 available"):
            purchases.assign_existing_stock_cost(
                replace(
                    command,
                    correlation_id=uuid4(),
                    idempotency_key="assign-too-much-legacy-cost",
                    expected_inventory_version=4,
                    quantity_scaled=11_000,
                )
            )

        current = assigned.current
        line = current.lines[0]
        invalid_correction = CorrectPurchaseCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            current.purchase_id,
            current.last_event_id,
            current.stream_version,
            purchases.correlation_id_for(owner.household_id, current.purchase_id),
            "invalid-existing-cost-base",
            "Remembered Supplier",
            "USD",
            None,
            None,
            datetime(2026, 8, 1, 12, tzinfo=UTC),
            0,
            0,
            0,
            1_800,
            (
                CorrectPurchaseLineCommand(
                    line.purchase_line_id,
                    line.inventory_item_id,
                    4,
                    10_000,
                    line.unit_code,
                    1_800,
                ),
            ),
            "Validate correction",
        )
        invalid_cases = (
            (
                replace(invalid_correction, idempotency_key="existing-cost-tax", tax_minor=1),
                "one amount",
            ),
            (
                replace(invalid_correction, idempotency_key="existing-cost-lines", lines=()),
                "one item",
            ),
            (
                replace(
                    invalid_correction,
                    idempotency_key="existing-cost-item",
                    lines=(replace(invalid_correction.lines[0], inventory_item_id=uuid4()),),
                ),
                "cannot change its item",
            ),
            (
                replace(
                    invalid_correction,
                    idempotency_key="existing-cost-subtotal",
                    lines=(replace(invalid_correction.lines[0], subtotal_minor=1_700),),
                ),
                "must match",
            ),
            (
                replace(
                    invalid_correction,
                    idempotency_key="existing-cost-version",
                    lines=(replace(invalid_correction.lines[0], expected_inventory_version=3),),
                ),
                "version is stale",
            ),
        )
        for invalid, message in invalid_cases:
            with pytest.raises(PurchaseValidationError, match=message):
                purchases.correct(invalid)
        corrected = purchases.correct(
            CorrectPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                current.purchase_id,
                current.last_event_id,
                current.stream_version,
                purchases.correlation_id_for(owner.household_id, current.purchase_id),
                "correct-legacy-cost",
                "Remembered Supplier",
                "USD",
                "Historical receipt",
                None,
                datetime(2026, 8, 1, 12, tzinfo=UTC),
                0,
                0,
                0,
                2_000,
                (
                    CorrectPurchaseLineCommand(
                        line.purchase_line_id,
                        line.inventory_item_id,
                        4,
                        10_000,
                        line.unit_code,
                        2_000,
                    ),
                ),
                "Correct remembered amount",
            )
        )
        _catch_up(engine, manager)
        assert purchases.cost_summary_for(owner.household_id, legacy.item_id).known_remaining == (
            CurrencyValue("USD", 2_000),
        )
        assert inventory.balance_for(
            owner.household_id, legacy.item_id
        ).on_hand_quantity_scaled == (20_000)

        voided = purchases.void(
            ControlPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                corrected.purchase_id,
                corrected.current.last_event_id,
                corrected.current.stream_version,
                purchases.correlation_id_for(owner.household_id, corrected.purchase_id),
                "void-legacy-cost",
                "Cost record not applicable",
            )
        )
        _catch_up(engine, manager)
        voided_summary = purchases.cost_summary_for(owner.household_id, legacy.item_id)
        assert voided_summary.known_remaining == ()
        assert voided_summary.unknown_remaining_quantity_scaled == 20_000
        assert inventory.balance_for(
            owner.household_id, legacy.item_id
        ).on_hand_quantity_scaled == (20_000)

        purchases.reinstate(
            ControlPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                voided.purchase_id,
                voided.current.last_event_id,
                voided.current.stream_version,
                purchases.correlation_id_for(owner.household_id, voided.purchase_id),
                "reinstate-legacy-cost",
                "Cost record confirmed",
            )
        )
        _catch_up(engine, manager)
        reinstated = purchases.cost_summary_for(owner.household_id, legacy.item_id)
        assert reinstated.known_remaining == (CurrencyValue("USD", 2_000),)
        assert reinstated.unknown_remaining_quantity_scaled == 10_000
        assert inventory.balance_for(
            owner.household_id, legacy.item_id
        ).on_hand_quantity_scaled == (20_000)
    finally:
        engine.dispose()


def test_feeding_deletion_restores_paid_stock_and_consumption_value(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, manager = _setup(tmp_path)
    try:
        animals = AnimalService(
            store,
            SQLAlchemyAnimalCurrentProjection(engine),
            inventory_projection=SQLAlchemyInventoryBalanceProjection(engine),
        )
        animal = animals.register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="costed-feeding-animal",
                name="Atlas",
                species="Python regius",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        acquired = purchases.acquire_new(
            AcquireNewInventoryCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                uuid4(),
                "costed-feeding-stock",
                "Small Frozen Rat",
                "food",
                "each",
                "whole_prey",
                "rat",
                "small",
                "frozen_thawed",
                None,
                20_000,
                4_000,
                "USD",
                "Rat Supplier",
                None,
                datetime(2026, 9, 11, 12, tzinfo=UTC),
            )
        )
        feeding = animals.record_inventory_feeding(
            RecordInventoryFeedingCommand(
                owner.household_id,
                owner.user_id,
                animal.animal_id,
                uuid4(),
                "costed-feeding",
                datetime.now(UTC) - timedelta(minutes=1),
                acquired.item_id,
                2,
                1_000,
                "accepted",
                None,
            )
        )
        _catch_up(engine, manager)
        after_feeding = purchases.cost_summary_for(owner.household_id, acquired.item_id)
        assert after_feeding.known_consumed == (CurrencyValue("USD", 200),)
        assert after_feeding.known_remaining == (CurrencyValue("USD", 3_800),)

        animals.delete_care_record(
            DeleteAnimalCareRecordCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "delete-costed-feeding",
            )
        )
        _catch_up(engine, manager)
        restored = purchases.cost_summary_for(owner.household_id, acquired.item_id)
        assert restored.known_consumed == ()
        assert restored.known_remaining == (CurrencyValue("USD", 4_000),)
        balance = inventory.balance_for(owner.household_id, acquired.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 20_000
    finally:
        engine.dispose()


def test_purchase_posts_atomic_receipts_and_one_cash_spend_fact(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Small Frozen Mouse", "mice")
        substrate = _item(inventory, owner, "Counted substrate", "substrate")
        posted = _post(
            purchases,
            owner,
            key="two-line-purchase",
            lines=(
                PurchaseLineCommand(mice.item_id, 1, 50_000, "each", 6_500),
                PurchaseLineCommand(substrate.item_id, 1, 10_000, "each", 2_000),
            ),
            tax=600,
            fee=100,
            discount=200,
            total=9_000,
        )

        assert posted.current.total_paid_minor == 9_000
        assert sum(line.allocated_cost_minor for line in posted.current.lines) == 9_000
        mice_balance = inventory.balance_for(owner.household_id, mice.item_id)
        substrate_balance = inventory.balance_for(owner.household_id, substrate.item_id)
        assert mice_balance is not None and mice_balance.on_hand_quantity_scaled == 50_000
        assert substrate_balance is not None and substrate_balance.on_hand_quantity_scaled == 10_000
        _catch_up(engine, manager)
        facts_table = _cash_facts_table(manager)
        with engine.connect() as connection:
            facts = connection.execute(
                text(
                    f'SELECT source_kind,source_id,amount_minor FROM "{facts_table}" '
                    "WHERE household_id=:household_id"
                ),
                {"household_id": str(owner.household_id)},
            ).all()
        assert facts == [("purchase", str(posted.purchase_id), 9_000)]
    finally:
        engine.dispose()


def test_fifo_and_cash_use_rebuildable_generation_boundaries(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Generated FIFO Mouse", "generated-fifo")
        posted = _post(
            purchases,
            owner,
            key="generated-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 2_000, "each", 201),),
            total=201,
        )

        pending = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert pending.available is True
        assert pending.lag_events > 0
        assert pending.known_remaining == ()

        _catch_up(engine, manager)
        expected = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert expected.lag_events == 0
        assert expected.known_remaining == (CurrencyValue("USD", 201),)
        cash_table = _cash_facts_table(manager)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        f'SELECT amount_minor FROM "{cash_table}" '
                        "WHERE source_kind='purchase' AND source_id=:source_id"
                    ),
                    {"source_id": str(posted.purchase_id)},
                ).scalar_one()
                == 201
            )

        manager.rebuild("inventory_costing")
        assert purchases.cost_summary_for(owner.household_id, mice.item_id) == expected
        manager.rollback("inventory_costing")
        assert purchases.cost_summary_for(owner.household_id, mice.item_id) == expected
    finally:
        engine.dispose()


def test_fifo_values_partial_lots_and_reconciles_final_remainder(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "FIFO Mouse", "fifo-mice")
        _post(
            purchases,
            owner,
            key="first-lot",
            lines=(PurchaseLineCommand(mice.item_id, 1, 3_000, "each", 100),),
            total=100,
        )
        _post(
            purchases,
            owner,
            key="second-lot",
            lines=(
                PurchaseLineCommand(
                    mice.item_id,
                    2,
                    2_000,
                    "each",
                    200,
                ),
            ),
            total=200,
        )
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None
        observed_costs = []
        for index, quantity in enumerate((1_000, 1_000, 2_000)):
            result = inventory.consume_scaled(
                ConsumeScaledStockCommand(
                    owner.household_id,
                    owner.user_id,
                    mice.item_id,
                    uuid4(),
                    f"consume-{index}",
                    3 + index,
                    quantity,
                    None,
                )
            )
            _catch_up(engine, manager)
            observed_costs.append(
                purchases.cost_summary_for(owner.household_id, mice.item_id)
                .known_consumed[0]
                .amount_minor
            )
            assert result.balance.on_hand_quantity_scaled == (4_000, 3_000, 1_000)[index]
        assert observed_costs == [33, 66, 200]
        summary = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert summary.known_remaining[0].amount_minor == 100
        assert summary.unknown_remaining_quantity_scaled == 0
    finally:
        engine.dispose()


def test_fifo_classifies_count_variance_and_expiry_without_inventing_cost(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Variance Mouse", "variance-mice")
        _post(
            purchases,
            owner,
            key="variance-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 5_000, "each", 500),),
            total=500,
        )
        inventory.adjust_scaled(
            AdjustScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "positive-count-variance",
                2,
                2_000,
                "Physical count found two extra.",
            )
        )
        inventory.adjust_scaled(
            AdjustScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "negative-count-variance",
                3,
                -1_000,
                "Physical count found one fewer.",
            )
        )
        inventory.expire(
            ExpireStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "expire-counted-stock",
                4,
                1,
                "Past safe-use date.",
            )
        )
        _catch_up(engine, manager)

        summary = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert summary.known_remaining == (CurrencyValue("USD", 300),)
        assert summary.unknown_remaining_quantity_scaled == 2_000
        activity = purchases.cost_activity_for(
            owner.household_id,
            mice.item_id,
            datetime(1970, 1, 1, tzinfo=UTC),
            datetime(2100, 1, 1, tzinfo=UTC),
        )
        assert activity.known_consumed == ()
        assert activity.known_expired == (CurrencyValue("USD", 100),)
        assert activity.known_variance == (CurrencyValue("USD", 100),)
        with engine.connect() as connection:
            allocation_table = manager.active_layout("inventory_costing").component(
                "inventory_costing", "allocations"
            )
            classifications = connection.execute(
                text(
                    f'SELECT classification,COUNT(*) FROM "{allocation_table}" '
                    "GROUP BY classification ORDER BY classification"
                )
            ).all()
        assert classifications == [("expiry", 1), ("variance", 1)]
    finally:
        engine.dispose()


def test_fifo_rebuild_rejects_depletion_without_an_effective_layer(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Corruption Guard Mouse", "corruption-guard-mice")
        posted = _post(
            purchases,
            owner,
            key="corruption-guard-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
        )
        inventory.expire(
            ExpireStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "corruption-guard-expiry",
                2,
                1,
                "Expired stock.",
            )
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE inventory_effective_receipts SET status='voided' "
                    "WHERE household_id=:household_id AND purchase_id=:purchase_id"
                ),
                {
                    "household_id": str(owner.household_id),
                    "purchase_id": str(posted.purchase_id),
                },
            )
        with pytest.raises(PurchaseValidationError, match="beyond effective stock layers"):
            manager.rebuild("inventory_costing")
    finally:
        engine.dispose()


def test_largest_remainder_is_exact_and_stably_tied() -> None:
    first, second = uuid4(), uuid4()
    allocated = allocate_acquisition_costs(1_101, ((first, 333), (second, 667)))
    assert sum(allocated.values()) == 1_101
    assert sorted(allocated.values()) == [367, 734]


def test_purchase_value_objects_reject_invalid_boundary_values() -> None:
    with pytest.raises(PurchaseValidationError, match="allocation inputs"):
        allocate_acquisition_costs(0, ((uuid4(), 1),))
    with pytest.raises(PurchaseValidationError, match="Vendor is required"):
        _required_text("   ", "Vendor", 200)
    with pytest.raises(PurchaseValidationError, match="Reference must be"):
        _optional_text("x" * 4, "Reference", 3)
    with pytest.raises(PurchaseValidationError, match="three-letter"):
        _currency("US1")
    with pytest.raises(PurchaseValidationError, match="positive monetary"):
        _positive_money(False, "Total")
    with pytest.raises(PurchaseValidationError, match="cannot be negative"):
        _nonnegative_money(-1, "Tax")
    with pytest.raises(PurchaseValidationError, match="quantity must be positive"):
        _quantity(1_000, "missing-unit", "Mouse")
    with pytest.raises(PurchaseValidationError, match="whole Each"):
        _quantity(1_500, "each", "Mouse")
    with pytest.raises(PurchaseValidationError, match="include a timezone"):
        _utc(datetime(2026, 9, 10, 12))

    source = uuid4()
    portions = (
        InventoryCostAssignmentPortionV1(source, 0, 5_000),
        InventoryCostAssignmentPortionV1(source, 5_000, 5_000),
    )
    assert _resize_assignment_portions(portions, 7_000) == (
        portions[0],
        InventoryCostAssignmentPortionV1(source, 5_000, 2_000),
    )
    assert _resize_assignment_portions(portions, 0) == ()
    assert _resize_assignment_portions((), 1_000) == ()
    with pytest.raises(PurchaseValidationError, match="acquisition type"):
        _acquisition_mode(
            PurchaseRecordedV2(uuid4(), "Vendor", "USD", None, 0, 0, 0, 100, (), "invalid")
        )


def test_unified_acquisition_rejects_invalid_item_and_assignment_boundaries(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        base = AcquireNewInventoryCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            uuid4(),
            "acquisition-validation-base",
            "Validation Mouse",
            "food",
            "each",
            "whole_prey",
            "mouse",
            "small",
            "frozen_thawed",
            None,
            1_000,
            0,
            "USD",
            None,
            None,
            datetime(2026, 9, 11, 12, tzinfo=UTC),
        )
        invalid_acquisitions = (
            (
                replace(base, idempotency_key="negative-acquisition", quantity_scaled=-1),
                "cannot be negative",
            ),
            (
                replace(base, idempotency_key="negative-threshold", reorder_threshold_scaled=-1),
                "threshold cannot be negative",
            ),
            (
                replace(
                    base,
                    idempotency_key="paid-zero-acquisition",
                    quantity_scaled=0,
                    amount_paid_minor=100,
                ),
                "positive quantity",
            ),
            (
                replace(base, idempotency_key="invalid-catalog", inventory_type="unknown"),
                "Inventory type",
            ),
        )
        for invalid, message in invalid_acquisitions:
            with pytest.raises(PurchaseValidationError, match=message):
                purchases.acquire_new(invalid)
        zero_threshold = purchases.acquire_new(
            replace(
                base,
                correlation_id=uuid4(),
                idempotency_key="zero-threshold-acquisition",
                reorder_threshold_scaled=0,
            )
        )
        assert zero_threshold.purchase_id is None

        legacy = inventory.register(
            RegisterInventoryItemCommand(
                owner.household_id,
                owner.user_id,
                uuid4(),
                "unconfigured-cost-assignment",
                "Unconfigured mouse",
                "item",
                None,
            )
        )
        assignment = AssignExistingStockCostCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            uuid4(),
            "unconfigured-cost-assignment",
            legacy.item_id,
            1,
            1_000,
            100,
            "USD",
            None,
            None,
            datetime(2026, 9, 11, 12, tzinfo=UTC),
        )
        with pytest.raises(PurchaseValidationError, match="Finish Inventory setup"):
            purchases.assign_existing_stock_cost(assignment)

        configured = _item(inventory, owner, "Stale Assignment Mouse", "stale-assignment-item")
        with pytest.raises(PurchaseValidationError, match="version is stale"):
            purchases.assign_existing_stock_cost(
                replace(
                    assignment,
                    idempotency_key="stale-cost-assignment",
                    inventory_item_id=configured.item_id,
                    expected_inventory_version=0,
                )
            )

        cost_projection = SQLAlchemyInventoryCostProjection(engine, manager)
        with pytest.raises(PurchaseValidationError, match="quantity must be positive"):
            cost_projection.assignment_portions_for(owner.household_id, configured.item_id, 0)
        with pytest.raises(PurchaseValidationError, match="is updating"):
            cost_projection.assignment_portions_for(owner.household_id, configured.item_id, 1_000)
    finally:
        engine.dispose()


def test_purchase_post_rejects_authorization_and_inventory_invariant_failures(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Validated Mouse", "validated-mice")
        archived = _item(inventory, owner, "Archived Mouse", "archived-validation-mice")
        inventory.archive_item(
            ArchiveInventoryItemCommand(
                owner.household_id,
                owner.user_id,
                archived.item_id,
                uuid4(),
                "archive-validation-mice",
                1,
                "Not currently stocked.",
            )
        )
        base = PostPurchaseCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            uuid4(),
            "validation-base",
            "Reptile Supply",
            "USD",
            None,
            None,
            datetime(2026, 9, 10, 12, tzinfo=UTC),
            0,
            0,
            0,
            100,
            (PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
        )

        cases = (
            (replace(base, actor_role="member"), "Only owners"),
            (replace(base, idempotency_key="no-lines", lines=()), "between 1 and 25"),
            (
                replace(
                    base,
                    idempotency_key="archived-item",
                    lines=(PurchaseLineCommand(archived.item_id, 2, 1_000, "each", 100),),
                ),
                "must be active and configured",
            ),
            (
                replace(
                    base,
                    idempotency_key="wrong-unit",
                    lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "gram", 100),),
                ),
                "must be received",
            ),
            (
                replace(
                    base,
                    idempotency_key="stale-version",
                    lines=(PurchaseLineCommand(mice.item_id, 0, 1_000, "each", 100),),
                ),
                "stale or inconsistent",
            ),
            (
                replace(
                    base,
                    idempotency_key="fractional-each",
                    lines=(PurchaseLineCommand(mice.item_id, 1, 1_500, "each", 100),),
                ),
                "requires a whole",
            ),
            (replace(base, idempotency_key="bad-vendor", vendor=""), "Vendor is required"),
            (replace(base, idempotency_key="bad-currency", currency="12"), "three-letter"),
            (
                replace(base, idempotency_key="long-reference", reference="x" * 301),
                "Purchase reference must be",
            ),
            (
                replace(base, idempotency_key="negative-tax", tax_minor=-1),
                "Tax cannot be negative",
            ),
            (
                replace(base, idempotency_key="zero-total", total_paid_minor=0),
                "Total paid must be a positive",
            ),
            (
                replace(base, idempotency_key="naive-time", occurred_at=datetime(2026, 9, 10, 12)),
                "include a timezone",
            ),
        )
        for command_value, message in cases:
            with pytest.raises(
                (PurchaseAuthorizationError, PurchaseValidationError), match=message
            ):
                purchases.post(command_value)
        assert purchases.list_purchases(owner.household_id) == ()
    finally:
        engine.dispose()


def test_purchase_projections_defend_atomic_receipt_and_control_invariants(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Projection Guard Mouse", "projection-guard-mice")
        posted = _post(
            purchases,
            owner,
            key="projection-guard-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
        )
        purchase_event = store.load_stream(
            StreamKey(owner.household_id, "purchase", posted.purchase_id)
        )[0]
        receipt_event = next(
            event
            for event in store.load_stream(
                StreamKey(owner.household_id, "inventory-item", mice.item_id)
            )
            if event.event_type == "inventory.stock_received"
        )
        line = PurchaseLineV1(
            posted.current.lines[0].purchase_line_id,
            mice.item_id,
            1_000,
            "each",
            100,
        )
        projection = SQLAlchemyPurchaseCurrentProjection(engine)

        with pytest.raises(PurchaseValidationError, match="missing its atomic receipt"):
            projection._validate_new_receipts(posted.purchase_id, (line,), {})
        with pytest.raises(PurchaseValidationError, match="does not match its line"):
            projection._validate_new_receipts(
                uuid4(), (line,), {line.purchase_line_id: receipt_event}
            )

        missing_control = replace(
            purchase_event,
            stream_id=uuid4(),
            stream_version=2,
            payload=EventVoidedV1(purchase_event.event_id, "Missing target"),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="control target is not effective"),
        ):
            projection.apply(connection, (missing_control,))

        receipt_projection = SQLAlchemyInventoryEffectiveReceiptProjection()
        missing_correction = replace(
            receipt_event,
            payload=InventoryReceiptCorrectedV1(uuid4(), 1_000, "Missing target"),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="correction target is missing"),
        ):
            receipt_projection.apply(connection, (missing_correction,))
        missing_receipt_control = replace(
            receipt_event,
            payload=EventVoidedV1(uuid4(), "Missing target"),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="control target is missing"),
        ):
            receipt_projection.apply(connection, (missing_receipt_control,))

        corrected_payload = PurchaseCorrectedV1(
            purchase_event.event_id,
            "Projection Guard Supply",
            "USD",
            None,
            0,
            0,
            0,
            100,
            (line,),
            "Projection invariant check.",
        )
        missing_companion = replace(
            purchase_event,
            stream_version=2,
            event_type="purchase.corrected",
            payload=corrected_payload,
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="missing its receipt correction"),
        ):
            projection.apply(connection, (missing_companion,))
        companion = replace(
            receipt_event,
            payload=InventoryReceiptCorrectedV1(receipt_event.event_id, 1_000, "Corrected receipt"),
        )
        ineffective_target = replace(
            missing_companion,
            payload=replace(corrected_payload, target_event_id=uuid4()),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="correction target is not effective"),
        ):
            projection.apply(connection, (ineffective_target, companion))
        moved_line = replace(line, inventory_item_id=uuid4())
        moved_event = replace(
            missing_companion,
            payload=replace(corrected_payload, lines=(moved_line,)),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="changed its Inventory Item"),
        ):
            projection.apply(connection, (moved_event,))
        removed_event = replace(
            missing_companion,
            payload=replace(corrected_payload, lines=()),
        )
        with (
            engine.begin() as connection,
            pytest.raises(PurchaseValidationError, match="missing its receipt void"),
        ):
            projection.apply(connection, (removed_event,))

        with pytest.raises(PurchaseValidationError, match="FIFO position is invalid"):
            _as_int("1", "FIFO position")
    finally:
        engine.dispose()


def test_purchase_correction_rejects_invalid_lifecycle_and_line_changes(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Correction Mouse", "correction-validation-mice")
        rats = _item(inventory, owner, "Correction Rat", "correction-validation-rats")
        posted = _post(
            purchases,
            owner,
            key="correction-validation-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        line_id = posted.current.lines[0].purchase_line_id
        valid_line = CorrectPurchaseLineCommand(line_id, mice.item_id, 2, 1_000, "each", 100)
        base = CorrectPurchaseCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            posted.purchase_id,
            posted.current.last_event_id,
            1,
            root.correlation_id,
            "correction-validation-base",
            "Reptile Supply",
            "USD",
            None,
            None,
            datetime(2026, 9, 10, 12, tzinfo=UTC),
            0,
            0,
            0,
            100,
            (valid_line,),
            "Correct the receipt.",
        )
        cases = (
            (replace(base, actor_role="administrator"), "Only the household owner"),
            (replace(base, idempotency_key="bad-lineage", correlation_id=uuid4()), "lineage"),
            (replace(base, idempotency_key="no-correction-lines", lines=()), "between 1 and 25"),
            (
                replace(
                    base,
                    idempotency_key="duplicate-lines",
                    lines=(
                        replace(valid_line, subtotal_minor=50),
                        replace(valid_line, subtotal_minor=50),
                    ),
                ),
                "cannot appear more than once",
            ),
            (
                replace(
                    base,
                    idempotency_key="unknown-item",
                    lines=(replace(valid_line, inventory_item_id=uuid4()),),
                ),
                "not in this household",
            ),
            (
                replace(
                    base,
                    idempotency_key="wrong-correction-unit",
                    lines=(replace(valid_line, unit_code="gram"),),
                ),
                "must be received",
            ),
            (
                replace(
                    base,
                    idempotency_key="stale-correction-item",
                    lines=(replace(valid_line, expected_inventory_version=1),),
                ),
                "stale or inconsistent",
            ),
            (
                replace(
                    base,
                    idempotency_key="unknown-purchase-line",
                    lines=(replace(valid_line, purchase_line_id=uuid4()),),
                ),
                "unknown line",
            ),
            (
                replace(
                    base,
                    idempotency_key="moved-purchase-line",
                    lines=(
                        replace(
                            valid_line,
                            inventory_item_id=rats.item_id,
                            expected_inventory_version=1,
                        ),
                    ),
                ),
                "cannot be moved",
            ),
            (
                replace(base, idempotency_key="wrong-correction-total", total_paid_minor=99),
                "must equal",
            ),
        )
        for command_value, message in cases:
            with pytest.raises(
                (PurchaseAuthorizationError, PurchaseValidationError), match=message
            ):
                purchases.correct(command_value)
        assert purchases.purchase_for(owner.household_id, posted.purchase_id) == posted.current
    finally:
        engine.dispose()


def test_purchase_controls_reject_invalid_targets_states_and_lineage(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Control Validation Mouse", "control-validation-mice")
        posted = _post(
            purchases,
            owner,
            key="control-validation-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        base = ControlPurchaseCommand(
            owner.household_id,
            owner.user_id,
            "owner",
            posted.purchase_id,
            posted.current.last_event_id,
            1,
            root.correlation_id,
            "control-validation-base",
            "Correct purchase history.",
        )
        invalid_cases = (
            (replace(base, actor_role="administrator"), "Only the household owner"),
            (
                replace(base, idempotency_key="missing-purchase", purchase_id=uuid4()),
                "does not exist",
            ),
            (replace(base, idempotency_key="stale-purchase", expected_stream_version=2), "stale"),
            (
                replace(base, idempotency_key="wrong-target", target_event_id=uuid4()),
                "effective event",
            ),
            (replace(base, idempotency_key="wrong-lineage", correlation_id=uuid4()), "lineage"),
        )
        for command_value, message in invalid_cases:
            with pytest.raises(
                (PurchaseAuthorizationError, PurchaseValidationError), match=message
            ):
                purchases.void(command_value)

        with pytest.raises(PurchaseValidationError, match="no active void"):
            purchases.reinstate(replace(base, idempotency_key="premature-reinstate"))
        valid_void = replace(base, idempotency_key="valid-void")
        voided = purchases.void(valid_void)
        assert purchases.void(valid_void) == voided
        with pytest.raises(PurchaseValidationError, match="already voided"):
            purchases.void(
                replace(
                    base,
                    idempotency_key="second-void",
                    target_event_id=voided.current.last_event_id,
                    expected_stream_version=2,
                )
            )
        with pytest.raises(PurchaseValidationError, match="reinstated before correction"):
            purchases.correct(
                CorrectPurchaseCommand(
                    owner.household_id,
                    owner.user_id,
                    "owner",
                    posted.purchase_id,
                    voided.current.last_event_id,
                    2,
                    root.correlation_id,
                    "correct-voided",
                    "Reptile Supply",
                    "USD",
                    None,
                    None,
                    datetime(2026, 9, 10, 12, tzinfo=UTC),
                    0,
                    0,
                    0,
                    100,
                    (
                        CorrectPurchaseLineCommand(
                            posted.current.lines[0].purchase_line_id,
                            mice.item_id,
                            3,
                            1_000,
                            "each",
                            100,
                        ),
                    ),
                    "Cannot correct while voided.",
                )
            )
        with pytest.raises(PurchaseValidationError, match="history is missing"):
            purchases.correlation_id_for(owner.household_id, uuid4())
    finally:
        engine.dispose()


def test_purchase_validation_rejects_total_mismatch_without_partial_receipts(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "No partial Mouse", "no-partial")
        with pytest.raises(PurchaseValidationError, match="Total paid"):
            _post(
                purchases,
                owner,
                key="invalid-total",
                lines=(PurchaseLineCommand(mice.item_id, 1, 5_000, "each", 500),),
                total=499,
            )
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 0
    finally:
        engine.dispose()


def test_purchase_correction_reconciles_receipt_balance_cash_and_fifo(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Corrected Mouse", "corrected-mice")
        posted = _post(
            purchases,
            owner,
            key="correctable-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 10_000, "each", 1_000),),
            total=1_000,
        )
        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "corrected-consumption",
                2,
                2_000,
                None,
            )
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        corrected = purchases.correct(
            CorrectPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                posted.purchase_id,
                posted.current.last_event_id,
                posted.current.stream_version,
                root.correlation_id,
                "correct-purchase",
                "Corrected Supply",
                "USD",
                "Corrected receipt",
                "Quantity and total corrected",
                datetime(2026, 9, 9, 12, tzinfo=UTC),
                0,
                0,
                0,
                800,
                (
                    CorrectPurchaseLineCommand(
                        posted.current.lines[0].purchase_line_id,
                        mice.item_id,
                        3,
                        8_000,
                        "each",
                        800,
                    ),
                ),
                "Receipt quantity was entered incorrectly.",
            )
        )
        assert corrected.current.vendor == "Corrected Supply"
        assert corrected.current.total_paid_minor == 800
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 6_000
        _catch_up(engine, manager)
        costs = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert costs.known_consumed == (CurrencyValue("USD", 200),)
        assert costs.known_remaining == (CurrencyValue("USD", 600),)
        facts_table = _cash_facts_table(manager)
        with engine.connect() as connection:
            cash = connection.execute(
                text(
                    f'SELECT counterparty,amount_minor,status FROM "{facts_table}" '
                    "WHERE source_kind='purchase' AND source_id=:purchase_id"
                ),
                {"purchase_id": str(posted.purchase_id)},
            ).one()
        assert cash == ("Corrected Supply", 800, "active")
    finally:
        engine.dispose()


def test_purchase_void_and_reinstate_are_atomic_with_receipts(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Controlled Mouse", "controlled-mice")
        posted = _post(
            purchases,
            owner,
            key="controlled-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 5_000, "each", 500),),
            total=500,
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        voided = purchases.void(
            ControlPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                posted.purchase_id,
                posted.current.last_event_id,
                posted.current.stream_version,
                root.correlation_id,
                "void-purchase",
                "Duplicate receipt.",
            )
        )
        assert voided.current.status == "voided"
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 0
        _catch_up(engine, manager)
        assert purchases.cost_summary_for(owner.household_id, mice.item_id).known_remaining == ()

        reinstated = purchases.reinstate(
            ControlPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                posted.purchase_id,
                posted.current.last_event_id,
                voided.current.stream_version,
                root.correlation_id,
                "reinstate-purchase",
                "Receipt was confirmed.",
            )
        )
        assert reinstated.current.status == "active"
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 5_000
        _catch_up(engine, manager)
        assert purchases.cost_summary_for(owner.household_id, mice.item_id).known_remaining == (
            CurrencyValue("USD", 500),
        )
    finally:
        engine.dispose()


def test_purchase_retry_is_idempotent_before_stale_version_validation(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Retry Mouse", "retry-mice")
        line = (PurchaseLineCommand(mice.item_id, 1, 5_000, "each", 500),)
        first = _post(
            purchases,
            owner,
            key="retry-purchase",
            lines=line,
            total=500,
        )
        second = _post(
            purchases,
            owner,
            key="retry-purchase",
            lines=line,
            total=500,
        )
        assert second.purchase_id == first.purchase_id
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 5_000
        _catch_up(engine, manager)
        facts_table = _cash_facts_table(manager)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM domain_events WHERE stream_type='purchase'")
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(f"SELECT COUNT(*) FROM \"{facts_table}\" WHERE source_kind='purchase'")
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_purchase_void_that_would_make_stock_negative_rolls_back_every_fact(
    tmp_path: Path,
) -> None:
    engine, owner, store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Protected Mouse", "protected-mice")
        posted = _post(
            purchases,
            owner,
            key="protected-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 5_000, "each", 500),),
            total=500,
        )
        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "protected-use",
                2,
                1_000,
                None,
            )
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        with pytest.raises(InventoryValidationError, match="already used or reserved"):
            purchases.void(
                ControlPurchaseCommand(
                    owner.household_id,
                    owner.user_id,
                    "owner",
                    posted.purchase_id,
                    posted.current.last_event_id,
                    posted.current.stream_version,
                    root.correlation_id,
                    "refused-void",
                    "Should fail atomically.",
                )
            )
        current = purchases.purchase_for(owner.household_id, posted.purchase_id)
        assert current is not None and current.status == "active" and current.stream_version == 1
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 4_000
        _catch_up(engine, manager)
        facts_table = _cash_facts_table(manager)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        f"SELECT status FROM \"{facts_table}\" WHERE source_kind='purchase' "
                        "AND source_id=:purchase_id"
                    ),
                    {"purchase_id": str(posted.purchase_id)},
                ).scalar_one()
                == "active"
            )
    finally:
        engine.dispose()


def test_purchase_supports_twenty_five_lines_on_one_item_and_rejects_twenty_six(
    tmp_path: Path,
) -> None:
    engine, owner, _store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Bulk Mouse", "bulk-mice")
        posted = _post(
            purchases,
            owner,
            key="twenty-five-lines",
            lines=tuple(
                PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 1) for _index in range(25)
            ),
            total=25,
        )
        assert len(posted.current.lines) == 25
        balance = inventory.balance_for(owner.household_id, mice.item_id)
        assert balance is not None
        assert balance.on_hand_quantity_scaled == 25_000
        assert balance.stream_version == 26
        with pytest.raises(PurchaseValidationError, match="between 1 and 25"):
            _post(
                purchases,
                owner,
                key="twenty-six-lines",
                lines=tuple(
                    PurchaseLineCommand(mice.item_id, 26, 1_000, "each", 1) for _index in range(26)
                ),
                total=26,
            )
        assert len(purchases.list_purchases(owner.household_id)) == 1
    finally:
        engine.dispose()


def test_fifo_orders_backdated_lots_and_keeps_unknown_cost_explicit(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = inventory.register_structured(
            RegisterStructuredInventoryItemCommand(
                owner.household_id,
                owner.user_id,
                uuid4(),
                "unknown-opening-layer",
                "Mixed Cost Mouse",
                "food",
                "each",
                "whole_prey",
                "mouse",
                "small",
                "frozen_thawed",
                None,
                2_000,
            )
        )
        _post(
            purchases,
            owner,
            key="later-usd-lot",
            lines=(PurchaseLineCommand(mice.item_id, 2, 2_000, "each", 200),),
            total=200,
            occurred_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        )
        _post(
            purchases,
            owner,
            key="backdated-eur-lot",
            lines=(PurchaseLineCommand(mice.item_id, 3, 2_000, "each", 100),),
            total=100,
            occurred_at=datetime(2026, 9, 9, 12, tzinfo=UTC),
        )
        # The backdated $1 lot is oldest by occurred time, despite later recording.
        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "consume-unknown",
                4,
                2_000,
                None,
            )
        )
        _catch_up(engine, manager)
        summary = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert summary.unknown_remaining_quantity_scaled == 2_000
        assert summary.known_consumed == (CurrencyValue("USD", 100),)
        # The later $2 lot is next; the opening layer stays explicitly uncosted.
        inventory.consume_scaled(
            ConsumeScaledStockCommand(
                owner.household_id,
                owner.user_id,
                mice.item_id,
                uuid4(),
                "consume-backdated",
                5,
                1_000,
                None,
            )
        )
        _catch_up(engine, manager)
        summary = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert summary.unknown_remaining_quantity_scaled == 2_000
        assert summary.known_consumed == (CurrencyValue("USD", 200),)
        assert summary.known_remaining == (CurrencyValue("USD", 100),)
    finally:
        engine.dispose()


def test_purchase_correction_can_add_and_remove_lines_atomically(tmp_path: Path) -> None:
    engine, owner, store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        removed_item = _item(inventory, owner, "Removed Mouse", "removed-item")
        retained_item = _item(inventory, owner, "Retained Mouse", "retained-item")
        added_item = _item(inventory, owner, "Added Mouse", "added-item")
        posted = _post(
            purchases,
            owner,
            key="line-change-purchase",
            lines=(
                PurchaseLineCommand(removed_item.item_id, 1, 2_000, "each", 200),
                PurchaseLineCommand(retained_item.item_id, 1, 3_000, "each", 300),
            ),
            total=500,
        )
        retained_line = next(
            line for line in posted.current.lines if line.inventory_item_id == retained_item.item_id
        )
        root = store.load_stream(StreamKey(owner.household_id, "purchase", posted.purchase_id))[0]
        corrected = purchases.correct(
            CorrectPurchaseCommand(
                owner.household_id,
                owner.user_id,
                "owner",
                posted.purchase_id,
                posted.current.last_event_id,
                1,
                root.correlation_id,
                "replace-lines",
                "Line Change Supply",
                "USD",
                None,
                None,
                datetime(2026, 9, 9, 12, tzinfo=UTC),
                0,
                0,
                0,
                900,
                (
                    CorrectPurchaseLineCommand(
                        retained_line.purchase_line_id,
                        retained_item.item_id,
                        2,
                        4_000,
                        "each",
                        400,
                    ),
                    CorrectPurchaseLineCommand(
                        None,
                        added_item.item_id,
                        1,
                        5_000,
                        "each",
                        500,
                    ),
                ),
                "Correct receipt lines.",
            )
        )
        assert len(corrected.current.lines) == 2
        balances = {
            item.item_id: item
            for item in inventory.list_balances(owner.household_id, status="active")
        }
        assert balances[removed_item.item_id].on_hand_quantity_scaled == 0
        assert balances[retained_item.item_id].on_hand_quantity_scaled == 4_000
        assert balances[added_item.item_id].on_hand_quantity_scaled == 5_000
        with engine.connect() as connection:
            statuses = connection.execute(
                text(
                    "SELECT status,COUNT(*) FROM inventory_effective_receipts "
                    "WHERE purchase_id=:purchase_id GROUP BY status ORDER BY status"
                ),
                {"purchase_id": str(posted.purchase_id)},
            ).all()
        assert statuses == [("active", 2), ("voided", 1)]
    finally:
        engine.dispose()


def test_purchase_reads_and_line_validation_are_household_isolated(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, _manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Private Mouse", "private-mice")
        posted = _post(
            purchases,
            owner,
            key="private-purchase",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
        )
        other = AccountRegistrationService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"m65-a2-purchase-secret-for-tests-only",
        ).register(
            AccountRegistrationCommand(
                "Other Home",
                "UTC",
                "other@example.com",
                "Other Owner",
                "correct horse battery staple",
                "other-registration",
                uuid4(),
            )
        )
        assert purchases.purchase_for(other.household_id, posted.purchase_id) is None
        with pytest.raises(PurchaseValidationError, match="not in this household"):
            purchases.post(
                PostPurchaseCommand(
                    other.household_id,
                    other.user_id,
                    "owner",
                    uuid4(),
                    "cross-household-purchase",
                    "Unsafe Supply",
                    "USD",
                    None,
                    None,
                    datetime(2026, 9, 10, 12, tzinfo=UTC),
                    0,
                    0,
                    0,
                    100,
                    (PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
                )
            )
        with pytest.raises(PurchaseValidationError, match="not active in this household"):
            purchases.assign_existing_stock_cost(
                AssignExistingStockCostCommand(
                    other.household_id,
                    other.user_id,
                    "owner",
                    uuid4(),
                    "cross-household-cost-assignment",
                    mice.item_id,
                    1,
                    1_000,
                    100,
                    "USD",
                    None,
                    None,
                    datetime(2026, 9, 10, 12, tzinfo=UTC),
                )
            )
    finally:
        engine.dispose()


def test_fifo_keeps_currencies_separate_without_exchange_rate_inference(tmp_path: Path) -> None:
    engine, owner, _store, inventory, purchases, manager = _setup(tmp_path)
    try:
        mice = _item(inventory, owner, "Currency Mouse", "currency-mice")
        _post(
            purchases,
            owner,
            key="usd-lot",
            lines=(PurchaseLineCommand(mice.item_id, 1, 1_000, "each", 100),),
            total=100,
            currency="USD",
        )
        _post(
            purchases,
            owner,
            key="eur-lot",
            lines=(PurchaseLineCommand(mice.item_id, 2, 1_000, "each", 200),),
            total=200,
            currency="EUR",
        )
        _catch_up(engine, manager)
        summary = purchases.cost_summary_for(owner.household_id, mice.item_id)
        assert summary.known_remaining == (
            CurrencyValue("EUR", 200),
            CurrencyValue("USD", 100),
        )
    finally:
        engine.dispose()
