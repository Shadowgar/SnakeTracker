from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    CorrectInventoryFeedingCommand,
    DeleteAnimalCareRecordCommand,
    RecordInventoryFeedingCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.inventory import (
    ArchiveInventoryItemCommand,
    ConfigureInventoryItemCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveScaledStockCommand,
    ReceiveStockCommand,
    RegisterInventoryItemCommand,
    RegisterStructuredInventoryItemCommand,
)
from snaketracker.domains.animals.contracts import (
    AnimalFeedingCorrectedV2,
    AnimalFeedingRecordedV2,
)
from snaketracker.domains.inventory.catalog import (
    parse_quantity_scaled,
    resolve_creation_unit_policy,
    units_for_type,
    validate_creation_unit,
)
from snaketracker.domains.inventory.contracts import InventoryStockReceivedV2
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.inventory.projections import SQLAlchemyInventoryBalanceProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.store import ExpectedVersionConflictError, StreamKey
from snaketracker.presentation.animal_care_views import present_care_event

ROOT = Path(__file__).parents[2]


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "structured-inventory.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"m65-a1-structured-inventory-secret",
    ).bootstrap(
        BootstrapCommand(
            household_name="Structured Inventory Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="m65-a1-bootstrap",
            correlation_id=uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    inventory_projection = SQLAlchemyInventoryBalanceProjection(engine)
    inventory = InventoryService(store, inventory_projection)
    animals = AnimalService(
        store,
        SQLAlchemyAnimalCurrentProjection(engine),
        inventory_projection=inventory_projection,
    )
    animal = animals.register(
        RegisterAnimalCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            "m65-a1-animal",
            "Atlas",
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
    return engine, bootstrap, store, inventory, animals, animal


def _food(inventory: InventoryService, bootstrap, *, unit: str = "each"):  # type: ignore[no-untyped-def]
    return inventory.register_structured(
        RegisterStructuredInventoryItemCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            f"food-{unit}",
            "Small Frozen Mouse" if unit == "each" else "Prepared diet",
            "food",
            unit,
            "whole_prey" if unit == "each" else "prepared_food",
            "mouse" if unit == "each" else None,
            "small" if unit == "each" else None,
            "frozen_thawed" if unit == "each" else None,
            None,
        )
    )


def test_controlled_catalog_enforces_type_aware_and_fixed_precision_quantities() -> None:
    assert "each" in {unit.code for unit in units_for_type("food")}
    assert "bale" not in {unit.code for unit in units_for_type("heating_lighting")}
    assert parse_quantity_scaled("24", "each") == 24_000
    assert parse_quantity_scaled("1.250", "pound") == 1_250
    assert parse_quantity_scaled("0", "each", allow_zero=True) == 0
    with pytest.raises(ValueError, match="whole numbers"):
        parse_quantity_scaled("1.250", "each")
    with pytest.raises(ValueError, match="three decimal"):
        parse_quantity_scaled("1.0001", "gram")


@pytest.mark.parametrize(
    ("inventory_type", "food_category", "category", "detail", "basis", "unit"),
    (
        ("food", "whole_prey", None, None, None, "each"),
        ("food", "insect", None, None, None, "each"),
        ("equipment", None, "monitoring", "thermometer", None, "each"),
        ("heating_lighting", None, "heat_bulb", "halogen_bulb", None, "each"),
        ("substrate_bedding", None, "brick", None, None, "brick"),
        ("supplement", None, "powder", None, None, "gram"),
    ),
)
def test_guided_catalog_resolves_fixed_and_filtered_unit_policies(
    inventory_type: str,
    food_category: str | None,
    category: str | None,
    detail: str | None,
    basis: str | None,
    unit: str,
) -> None:
    policy = resolve_creation_unit_policy(inventory_type, food_category, category, detail, basis)
    assert validate_creation_unit("", policy) == unit
    if inventory_type == "supplement":
        assert policy.unit_codes == ("gram", "kilogram", "ounce", "pound")
        with pytest.raises(ValueError, match="not available"):
            validate_creation_unit("gallon", policy)


def test_structured_registration_atomically_establishes_uncosted_initial_stock_and_retries(
    tmp_path: Path,
) -> None:
    engine, bootstrap, store, inventory, _animals, _animal = _setup(tmp_path)
    try:
        command_value = RegisterStructuredInventoryItemCommand(
            household_id=bootstrap.household_id,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
            idempotency_key="initial-small-rats",
            name="Small Frozen Rat",
            inventory_type="food",
            unit_code="each",
            food_category="whole_prey",
            food_type="rat",
            size_stage="small",
            preparation_method="frozen_thawed",
            reorder_threshold_scaled=5_000,
            starting_quantity_scaled=20_000,
        )
        created = inventory.register_structured(command_value)
        assert created.balance.on_hand_quantity_scaled == 20_000
        assert created.balance.stream_version == 2
        events = store.load_stream(
            StreamKey(bootstrap.household_id, "inventory-item", created.item_id)
        )
        assert len(events) == 2
        assert isinstance(events[1].payload, InventoryStockReceivedV2)
        assert events[1].payload.reference == "Initial stock"
        assert events[1].causation_id == events[0].event_id

        retried = inventory.register_structured(command_value)
        assert retried.item_id == created.item_id
        assert retried.balance.on_hand_quantity_scaled == 20_000
        assert (
            len(
                store.load_stream(
                    StreamKey(bootstrap.household_id, "inventory-item", created.item_id)
                )
            )
            == 2
        )

        zero = inventory.register_structured(
            RegisterStructuredInventoryItemCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="zero-thermometer",
                name="Thermometer",
                inventory_type="equipment",
                unit_code="each",
                food_category=None,
                food_type=None,
                size_stage=None,
                preparation_method=None,
                reorder_threshold_scaled=None,
                starting_quantity_scaled=0,
            )
        )
        assert zero.balance.on_hand_quantity_scaled == 0
        assert zero.balance.stream_version == 1
    finally:
        engine.dispose()


def test_invalid_starting_stock_does_not_leave_an_orphan_item(tmp_path: Path) -> None:
    engine, bootstrap, _store, inventory, _animals, _animal = _setup(tmp_path)
    try:
        with engine.connect() as connection:
            before = connection.execute(
                text("SELECT COUNT(*) FROM domain_events WHERE stream_type='inventory-item'")
            ).scalar_one()
        with pytest.raises(InventoryValidationError, match="whole numbers"):
            inventory.register_structured(
                RegisterStructuredInventoryItemCommand(
                    household_id=bootstrap.household_id,
                    actor_user_id=bootstrap.user_id,
                    correlation_id=uuid4(),
                    idempotency_key="invalid-fractional-rats",
                    name="Fractional Rat",
                    inventory_type="food",
                    unit_code="each",
                    food_category="whole_prey",
                    food_type="rat",
                    size_stage="small",
                    preparation_method="frozen_thawed",
                    reorder_threshold_scaled=None,
                    starting_quantity_scaled=1_500,
                )
            )
        with engine.connect() as connection:
            after = connection.execute(
                text("SELECT COUNT(*) FROM domain_events WHERE stream_type='inventory-item'")
            ).scalar_one()
        assert after == before
    finally:
        engine.dispose()


def test_inventory_authoritative_feeding_snapshots_corrects_and_compensates(
    tmp_path: Path,
) -> None:
    engine, bootstrap, store, inventory, animals, animal = _setup(tmp_path)
    try:
        food = _food(inventory, bootstrap)
        received = inventory.receive_scaled(
            ReceiveScaledStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                food.item_id,
                uuid4(),
                "receive-food",
                1,
                5_000,
                "Qualification stock",
            )
        )
        feeding_command = RecordInventoryFeedingCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            animal.animal_id,
            uuid4(),
            "inventory-feeding",
            datetime(2026, 9, 10, 12, tzinfo=UTC),
            food.item_id,
            received.balance.stream_version,
            1_000,
            "accepted",
            None,
        )
        feeding = animals.record_inventory_feeding(feeding_command)
        assert feeding.event.schema_version == 2
        assert isinstance(feeding.event.payload, AnimalFeedingRecordedV2)
        assert feeding.event.payload.item_name == "Small Frozen Mouse"
        after_feeding = inventory.balance_for(bootstrap.household_id, food.item_id)
        assert after_feeding is not None and after_feeding.on_hand_quantity_scaled == 4_000
        retry = animals.record_inventory_feeding(feeding_command)
        assert retry.event.event_id == feeding.event.event_id
        after_retry = inventory.balance_for(bootstrap.household_id, food.item_id)
        assert after_retry is not None and after_retry.on_hand_quantity_scaled == 4_000

        corrected = animals.correct_inventory_feeding(
            CorrectInventoryFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                feeding.event.event_id,
                "correct-inventory-feeding",
                datetime(2026, 9, 10, 13, tzinfo=UTC),
                "refused",
                "Food and amount retained.",
            )
        )
        assert isinstance(corrected.event.payload, AnimalFeedingCorrectedV2)
        assert corrected.event.payload.item_name == "Small Frozen Mouse"
        after_correction = inventory.balance_for(bootstrap.household_id, food.item_id)
        assert after_correction is not None and after_correction.on_hand_quantity_scaled == 4_000

        renamed = inventory.configure_item(
            ConfigureInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                food.item_id,
                uuid4(),
                "rename-food",
                after_correction.stream_version,
                "Renamed Mouse",
                "food",
                "each",
                "whole_prey",
                "mouse",
                "small",
                "frozen_thawed",
                None,
            )
        )
        assert renamed.balance.name == "Renamed Mouse"
        assert "Small Frozen Mouse" in present_care_event(corrected.event).description

        animals.delete_care_record(
            DeleteAnimalCareRecordCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                corrected.event.event_id,
                "delete-inventory-feeding",
            )
        )
        final = inventory.balance_for(bootstrap.household_id, food.item_id)
        assert final is not None and final.on_hand_quantity_scaled == 5_000
        link = inventory.consumption_for_source(bootstrap.household_id, feeding.event.event_id)
        assert link is not None and link.status == "reversed" and link.schema_version == 2
        events = store.load_stream(StreamKey(bootstrap.household_id, "animal", animal.animal_id))
        assert feeding.event in events and corrected.event in events
    finally:
        engine.dispose()


def test_new_feeding_rejects_nonfood_legacy_archived_cross_household_and_stock_errors(
    tmp_path: Path,
) -> None:
    engine, bootstrap, _store, inventory, animals, animal = _setup(tmp_path)
    try:
        legacy = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "legacy-item",
                "Legacy mouse",
                "item",
                None,
            )
        )
        equipment = inventory.register_structured(
            RegisterStructuredInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "equipment-item",
                "Heat lamp",
                "equipment",
                "each",
                None,
                None,
                None,
                None,
                None,
            )
        )
        food = _food(inventory, bootstrap)
        received = inventory.receive_scaled(
            ReceiveScaledStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                food.item_id,
                uuid4(),
                "receive-one-food",
                1,
                1_000,
                None,
            )
        )

        def command_for(item_id, version, quantity=1_000, household_id=None):  # type: ignore[no-untyped-def]
            return RecordInventoryFeedingCommand(
                household_id or bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                str(uuid4()),
                datetime(2026, 9, 10, 12, tzinfo=UTC),
                item_id,
                version,
                quantity,
                "accepted",
                None,
            )

        with pytest.raises(AnimalValidationError, match="Finish Inventory setup"):
            animals.record_inventory_feeding(command_for(legacy.item_id, 1))
        with pytest.raises(AnimalValidationError, match="Food Inventory Item"):
            animals.record_inventory_feeding(command_for(equipment.item_id, 1))
        with pytest.raises(AnimalValidationError, match="positive"):
            animals.record_inventory_feeding(command_for(food.item_id, 2, 0))
        with pytest.raises(AnimalValidationError, match="positive"):
            animals.record_inventory_feeding(command_for(food.item_id, 2, -1_000))
        with pytest.raises(InventoryValidationError, match="Insufficient"):
            animals.record_inventory_feeding(command_for(food.item_id, 2, 2_000))
        with pytest.raises(ExpectedVersionConflictError):
            animals.record_inventory_feeding(command_for(food.item_id, 1))
        with pytest.raises(AnimalValidationError, match="does not exist in this household"):
            animals.record_inventory_feeding(command_for(food.item_id, 2, household_id=uuid4()))

        archived = inventory.archive_item(
            ArchiveInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                food.item_id,
                uuid4(),
                "archive-food",
                received.balance.stream_version,
                "Not active.",
            )
        )
        with pytest.raises(AnimalValidationError, match="active Food"):
            animals.record_inventory_feeding(
                command_for(food.item_id, archived.balance.stream_version)
            )
    finally:
        engine.dispose()


def test_fractional_food_feeding_uses_exact_thousandths(tmp_path: Path) -> None:
    engine, bootstrap, _store, inventory, animals, animal = _setup(tmp_path)
    try:
        food = _food(inventory, bootstrap, unit="pound")
        received = inventory.receive_scaled(
            ReceiveScaledStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                food.item_id,
                uuid4(),
                "receive-fractional-food",
                1,
                1_250,
                None,
            )
        )
        feeding = animals.record_inventory_feeding(
            RecordInventoryFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "fractional-food-feeding",
                datetime(2026, 9, 10, 12, tzinfo=UTC),
                food.item_id,
                received.balance.stream_version,
                250,
                "refused",
                None,
            )
        )
        assert isinstance(feeding.event.payload, AnimalFeedingRecordedV2)
        assert feeding.event.payload.quantity_scaled == 250
        balance = inventory.balance_for(bootstrap.household_id, food.item_id)
        assert balance is not None and balance.on_hand_quantity_scaled == 1_000
    finally:
        engine.dispose()


def test_catalog_rejects_irrelevant_food_fields_and_invalid_type_unit_pair(
    tmp_path: Path,
) -> None:
    engine, bootstrap, _store, inventory, _animals, _animal = _setup(tmp_path)
    try:
        with pytest.raises(InventoryValidationError, match="only available for Food"):
            inventory.register_structured(
                RegisterStructuredInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "equipment-with-food-fields",
                    "Heat lamp",
                    "equipment",
                    "each",
                    "whole_prey",
                    "mouse",
                    "small",
                    "frozen_thawed",
                    None,
                )
            )
        with pytest.raises(InventoryValidationError, match="not used"):
            inventory.register_structured(
                RegisterStructuredInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "prepared-with-prey-fields",
                    "Prepared diet",
                    "food",
                    "pound",
                    "prepared_food",
                    "mouse",
                    None,
                    None,
                    None,
                )
            )
        with pytest.raises(InventoryValidationError, match="not available"):
            inventory.register_structured(
                RegisterStructuredInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "bulb-by-bale",
                    "Heat lamp",
                    "heating_lighting",
                    "bale",
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
    finally:
        engine.dispose()


def test_legacy_setup_preserves_stock_and_rejects_ambiguous_unit_reinterpretation(
    tmp_path: Path,
) -> None:
    engine, bootstrap, _store, inventory, _animals, _animal = _setup(tmp_path)
    try:
        exact = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "legacy-exact",
                "Legacy feeder",
                "item",
                None,
            )
        )
        inventory.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                exact.item_id,
                uuid4(),
                "legacy-exact-stock",
                1,
                3,
                None,
            )
        )
        configured = inventory.configure_item(
            ConfigureInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                exact.item_id,
                uuid4(),
                "legacy-exact-setup",
                2,
                "Legacy feeder",
                "food",
                "each",
                "whole_prey",
                "mouse",
                "small",
                "frozen_thawed",
                None,
            )
        )
        assert configured.balance.on_hand_quantity_scaled == 3_000
        assert configured.balance.legacy_unit == "item"

        ambiguous = inventory.register(
            RegisterInventoryItemCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "legacy-ambiguous",
                "Legacy tub",
                "tub",
                None,
            )
        )
        inventory.receive(
            ReceiveStockCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                ambiguous.item_id,
                uuid4(),
                "legacy-ambiguous-stock-stock",
                1,
                2,
                None,
            )
        )
        with pytest.raises(InventoryValidationError, match="cannot be reinterpreted safely"):
            inventory.configure_item(
                ConfigureInventoryItemCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    ambiguous.item_id,
                    uuid4(),
                    "legacy-ambiguous-setup",
                    2,
                    "Legacy tub",
                    "equipment",
                    "each",
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
        preserved = inventory.balance_for(bootstrap.household_id, ambiguous.item_id)
        assert preserved is not None
        assert preserved.needs_setup and preserved.on_hand_quantity_scaled == 2_000
        assert preserved.legacy_unit == "tub"
    finally:
        engine.dispose()
