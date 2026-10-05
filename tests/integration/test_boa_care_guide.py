from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from snaketracker.application.animals import RecordInventoryFeedingCommand
from snaketracker.application.care_guides import grouped_claims
from snaketracker.application.inventory import ReceiveScaledStockCommand
from snaketracker.application.reminders import ReminderFactService, ReminderRuleService
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.taxonomy.care_guides import (
    CareGuideImportError,
    SQLAlchemyCareGuideRepository,
)
from snaketracker.operations.import_care_guides import load_bundle
from tests.integration.test_household_bootstrap import migrated_engine
from tests.integration.test_reminders import _rule_command
from tests.integration.test_structured_inventory_feeding import _food, _setup

ROOT = Path(__file__).parents[2]
BOA_BUNDLE = ROOT / "reference/care-guides/reviewed-boa-constrictor-v1.json"
REFERENCE_TABLES = {
    "care_guide_versions",
    "care_guide_current",
    "care_guide_sources",
    "care_guide_claims",
}


def _table_hashes(database: Path) -> dict[str, str]:
    """Independently hash every non-guide table, including household events/projections."""
    with sqlite3.connect(database) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        hashes = {}
        for (table,) in tables:
            if table in REFERENCE_TABLES:
                continue
            quoted = '"' + table.replace('"', '""') + '"'
            rows = sorted(repr(tuple(row)) for row in connection.execute(f"SELECT * FROM {quoted}"))
            hashes[table] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        return hashes


def _cache_taxon(database: Path, name: str, group: str = "snake") -> str:
    taxon_id = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO taxa (taxon_id,supported_group,accepted_scientific_name,"
            "taxonomic_status,created_at,refreshed_at) VALUES (?,?,?,'accepted',?,?)",
            (taxon_id, group, name, "2026-10-01T07:00:00+00:00", "2026-10-01T07:00:00+00:00"),
        )
    return taxon_id


def test_boa_bundle_has_species_scoped_provenance_and_preserves_disagreement() -> None:
    assert BOA_BUNDLE.is_file(), "Reviewed Boa constrictor bundle is missing"
    bundle = load_bundle(BOA_BUNDLE)
    assert len(bundle.guides) == 1
    guide = bundle.guides[0]
    assert guide.scientific_name == "Boa constrictor"
    assert guide.version == 1
    sources = {source.source_id: source for source in guide.sources}
    assert {source.publisher for source in guide.sources} == {
        "Royal Veterinary College",
        "ReptiFiles",
    }
    for source in guide.sources:
        assert source.title and source.url.startswith("https://")
        assert source.retrieved_at.date() == date(2026, 10, 1)
        assert source.retrieved_at <= source.reviewed_at <= guide.reviewed_at <= datetime.now(UTC)
    for claim in guide.claims:
        assert claim.source_id in sources
        assert claim.scope == "Boa constrictor"
        assert claim.context
    facts = {
        claims[0].fact_key: (claims, state)
        for _, groups in grouped_claims(guide)
        for _, claims, state in groups
    }
    cool, state = facts["cool_side_temperature"]
    assert state == "Sources differ"
    assert {(claim.value_number, claim.minimum, claim.maximum) for claim in cool} == {
        (25, None, None),
        (None, 24, 26),
    }
    assert facts["ambient_humidity"][1] == "Sources differ"
    assert facts["food_types"][1] == "Corroborated"
    assert facts["feeding_interval"][1] == "Single source"
    assert any("Boa imperator" in (claim.value_text or "") for claim in guide.claims)
    assert hashlib.sha256(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    ).hexdigest() == ("fd3e4d6e8d96173a51cfe7d7f5c20ecbfe24aae68127a3481f42a99e05097500")


def test_boa_import_is_idempotent_and_preserves_populated_household_tables(tmp_path: Path) -> None:
    bundle = load_bundle(BOA_BUNDLE)
    # Populate real command/projection paths without repeating the entire owner
    # browser rehearsal inside this import-invariance test's 30-second budget.
    fixture_engine, bootstrap, store, inventory, animals, animal = _setup(tmp_path)
    database = tmp_path / "structured-inventory.sqlite3"
    try:
        food = _food(inventory, bootstrap)
        received = inventory.receive_scaled(
            ReceiveScaledStockCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                item_id=food.item_id,
                correlation_id=uuid4(),
                idempotency_key="boa-fixture-stock",
                expected_stream_version=food.balance.stream_version,
                occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
                quantity_scaled=5000,
                reference="Fictional stock",
            )
        )
        animals.record_inventory_feeding(
            RecordInventoryFeedingCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                inventory_item_id=food.item_id,
                inventory_expected_stream_version=received.balance.stream_version,
                correlation_id=uuid4(),
                idempotency_key="boa-fixture-feeding",
                occurred_at=datetime(2026, 8, 10, tzinfo=UTC),
                inventory_quantity_scaled=1000,
                outcome="accepted",
                notes=None,
            )
        )
        projection = SQLAlchemyReminderProjection(fixture_engine)
        rule = ReminderRuleService(store, projection).create(
            _rule_command(bootstrap, animal.animal_id)
        )
        ReminderFactService(store, projection).recalculate_rule(
            bootstrap.household_id, rule.rule_id, now=datetime(2026, 8, 21, tzinfo=UTC)
        )
    finally:
        fixture_engine.dispose()
    taxon_id = _cache_taxon(database, "Boa constrictor")
    original = load_bundle(ROOT / "reference/care-guides/reviewed-v1.json")
    for guide in original.guides:
        _cache_taxon(database, guide.scientific_name, guide.biological_group.value)
    with sqlite3.connect(database) as connection:
        for table in (
            "domain_events",
            "animal_current",
            "reminder_rule_current",
            "reminder_facts",
            "inventory_balance",
        ):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
    before = _table_hashes(database)
    engine = create_sqlite_engine(database, require_local_storage=False)
    repo = SQLAlchemyCareGuideRepository(engine)
    try:
        assert repo.import_bundle(original) == (5, 0)
        assert repo.import_bundle(bundle) == (1, 0)
        assert repo.import_bundle(bundle) == (0, 1)
        assert repo.import_bundle(original) == (0, 5)
        assert _table_hashes(database) == before
        with sqlite3.connect(database) as connection:
            saved_sources = connection.execute(
                "SELECT source_id,publisher,title,url,retrieved_at,reviewed_at "
                "FROM care_guide_sources WHERE taxon_id=?",
                (taxon_id,),
            ).fetchall()
            assert set(saved_sources) == {
                (
                    source.source_id,
                    source.publisher,
                    source.title,
                    source.url,
                    source.retrieved_at.isoformat(),
                    source.reviewed_at.isoformat(),
                )
                for source in bundle.guides[0].sources
            }
            saved_claims = connection.execute(
                "SELECT claim_id,source_id,scope,context,value_text,value_number,minimum,maximum,"
                "unit,qualifier,life_stage,caution FROM care_guide_claims WHERE taxon_id=?",
                (taxon_id,),
            ).fetchall()
            assert set(saved_claims) == {
                (
                    claim.claim_id,
                    claim.source_id,
                    claim.scope,
                    claim.context,
                    claim.value_text,
                    claim.value_number,
                    claim.minimum,
                    claim.maximum,
                    claim.unit,
                    claim.qualifier,
                    claim.life_stage,
                    claim.caution,
                )
                for claim in bundle.guides[0].claims
            }
    finally:
        engine.dispose()


def test_boa_bundle_cannot_import_against_only_a_boa_imperator_taxon(tmp_path: Path) -> None:
    database = tmp_path / "wrong-boa-species.sqlite3"
    engine = migrated_engine(database)
    _cache_taxon(database, "Boa imperator")
    before = _table_hashes(database)
    try:
        with pytest.raises(CareGuideImportError, match=r"exactly one cached.*Boa constrictor"):
            SQLAlchemyCareGuideRepository(engine).import_bundle(load_bundle(BOA_BUNDLE))
        assert _table_hashes(database) == before
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT count(*) FROM care_guide_versions").fetchone() == (0,)
    finally:
        engine.dispose()
