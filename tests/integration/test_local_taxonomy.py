from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.local_taxonomy import GenerationSource, TaxonomyConflictError
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 10, 17, tzinfo=UTC)


@pytest.fixture
def catalog(tmp_path):
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{tmp_path / 'x2.db'}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(tmp_path / "x2.db", require_local_storage=False)
    yield LocalTaxonomyCatalog(engine)
    engine.dispose()


def taxon(identifier="1", name="Rana temporaria", group="", **kwargs):
    return ProviderTaxon(
        provider="fixture",
        provider_id=identifier,
        source_url="https://example.test/taxon/" + identifier,
        supported_group=group,
        accepted_scientific_name=name,
        **kwargs,
    )


def source(label):
    return GenerationSource(
        label=label,
        provider="fixture",
        source_url="https://example.test/archive",
        retrieved_at=NOW,
        snapshot_at=NOW - timedelta(days=10),
        checksum="a" * 64,
        rights="Synthetic fixture; no external archive rights asserted",
    )


def stage(catalog, label, records):
    generation = catalog.begin_generation(source(label), imported_at=NOW)
    catalog.stage(generation, records)
    catalog.validate_generation(generation)
    return generation


def test_permanent_identity_namespaces_homonyms_and_duplicate_races(catalog):
    candidate = taxon()
    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(
            pool.map(lambda _: catalog.publish(candidate, retrieved_at=NOW), range(8))
        )
    assert len(set(identifiers)) == 1
    other = catalog.publish(replace(candidate, provider="other"), retrieved_at=NOW)
    assert other != identifiers[0]
    assert len(catalog.search("Rana")) == 2
    with pytest.raises(TaxonomyConflictError):
        catalog.map_identity(
            identifiers[0],
            "other",
            "1",
            source_url="https://example.test",
            decided_by="operator",
            reason="explicit proposed mapping",
        )
    assert catalog.resolve(other).taxon_id == other
    assert len(catalog.conflicts()) == 1


def test_promotion_rollback_cleanup_retains_new_identity_and_live_discovery(catalog):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    b = catalog.begin_generation(source("B"), imported_at=NOW)
    catalog.stage(
        b,
        [
            taxon("2", "Ambystoma mexicanum", class_name="Amphibia", parent_provider_id="root"),
            taxon("root", "Animalia"),
        ],
    )
    live = catalog.publish(
        taxon("live", "Live discovery", synonyms=("Old discovery",)),
        retrieved_at=NOW,
        source_effective_at=NOW,
    )
    catalog.validate_generation(b)
    catalog.promote(b)
    introduced = catalog.search("Ambystoma")[0]
    assert introduced.workflow_group is None
    assert introduced.ancestry[0].scientific_name == "Animalia"
    assert catalog.search("Amphibia")[0].taxon_id == introduced.taxon_id
    catalog.promote(a)
    assert catalog.resolve(introduced.taxon_id).reference_state == "catalog_fallback"
    assert catalog.search("Ambystoma")[0].taxon_id == introduced.taxon_id
    assert catalog.search("Old discovery")[0].taxon_id == live
    catalog.cleanup(b, retained_generations={a})
    assert catalog.resolve(live) is not None
    assert catalog.resolve(introduced.taxon_id) is not None
    with pytest.raises(ValueError, match=r"retained|active"):
        catalog.cleanup(a, retained_generations=set())


def test_fresh_overlay_wins_older_snapshot_and_unknown_order_is_explicit(catalog):
    identifier = catalog.publish(taxon(name="New name"), retrieved_at=NOW, source_effective_at=NOW)
    b = stage(catalog, "B", [taxon(name="Old name")])
    catalog.promote(b)
    assert catalog.resolve(identifier).scientific_name == "New name"
    assert catalog.resolve(identifier).selection_state == "selected"
    assert catalog.search("Old name")[0].taxon_id == identifier
    catalog.publish(taxon(name="Unknown name"), retrieved_at=NOW + timedelta(days=1))
    summary = catalog.resolve(identifier)
    assert summary.scientific_name == "New name"
    assert summary.selection_state == "unknown_order"
    assert catalog.conflicts()


def test_failed_validation_and_bounded_reconciliation_keep_active_generation(catalog):
    a = stage(catalog, "A", [taxon()])
    catalog.promote(a)
    b = catalog.begin_generation(source("B"), imported_at=NOW)
    catalog.stage(b, [taxon("bad", parent_provider_id="absent")])
    with pytest.raises(ValueError, match="parent"):
        catalog.validate_generation(b)
    assert catalog.active_generation() == a
    c = stage(catalog, "C", [taxon()])
    catalog.publish(taxon("live"), retrieved_at=NOW)
    with pytest.raises(ValueError, match="reconciliation"):
        catalog.promote(c, max_revisions=0)
    assert catalog.active_generation() == a


def test_writer_at_promotion_boundary_remains_searchable(catalog):
    a = stage(catalog, "A", [taxon()])
    b = stage(catalog, "B", [taxon("2")])
    catalog.promote(a)
    with ThreadPoolExecutor(max_workers=2) as pool:
        promotion = pool.submit(catalog.promote, b)
        discovery = pool.submit(
            catalog.publish, taxon("race", "Boundary discovery"), retrieved_at=NOW
        )
        promotion.result()
        identifier = discovery.result()
    assert catalog.active_generation() == b
    assert catalog.search("Boundary")[0].taxon_id == identifier


def test_cycles_duplicate_rows_and_unresolved_replacements_block_promotion(catalog):
    generation = catalog.begin_generation(source("cycle"), imported_at=NOW)
    catalog.stage(
        generation, [taxon("1", parent_provider_id="2"), taxon("2", parent_provider_id="1")]
    )
    with pytest.raises(ValueError, match="cycle"):
        catalog.validate_generation(generation)
    duplicate = catalog.begin_generation(source("duplicate"), imported_at=NOW)
    with pytest.raises(ValueError, match="duplicate"):
        catalog.stage(duplicate, [taxon(), taxon()])
    replacement = catalog.begin_generation(source("replacement"), imported_at=NOW)
    catalog.stage(
        replacement,
        [taxon(accepted_provider_id="2", taxonomic_status="synonym"), taxon("2", "Replacement")],
    )
    catalog.validate_generation(replacement)
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(replacement)
    conflict = catalog.conflicts()[0]
    catalog.resolve_conflict(
        conflict.conflict_id, decided_by="owner", reason="retain separate identities"
    )
    catalog.promote(replacement)
    assert (
        next(
            record for record in catalog.search("Rana") if record.provider_id == "1"
        ).taxonomic_status
        == "synonym"
    )


def test_search_is_local_indexed_unicode_and_bounded(catalog):
    identifier = catalog.publish(
        taxon(
            preferred_common_name="Grenouille rousse",
            alternative_common_names=("Écarlate frog",),
            synonyms=("Historical frog",),
        ),
        retrieved_at=NOW,
    )
    for query in ("Rana", "rous", "écarl", "Historical"):
        assert catalog.search(query)[0].taxon_id == identifier
    assert catalog.search("nonexistent") == ()
    for query in ("x", "a" * 101, '" OR *'):
        with pytest.raises(ValueError):
            catalog.search(query, limit=100)
    with catalog.engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT taxon_id FROM taxonomy_search WHERE taxonomy_search MATCH ?",
            ('"rana"*',),
        ).all()
        assert any("VIRTUAL TABLE INDEX" in row[3] for row in plan)
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []


def test_explicit_cross_provider_mapping_retains_both_sources_and_unknown_order(catalog):
    identifier = catalog.publish(taxon(name="First source name"), retrieved_at=NOW)
    catalog.map_identity(
        identifier,
        "other",
        "same",
        source_url="https://example.test/other",
        decided_by="owner",
        reason="qualified same biological identity",
    )
    catalog.publish(
        replace(taxon("same", "Conflicting second source"), provider="other"),
        retrieved_at=NOW + timedelta(days=1),
    )
    summary = catalog.resolve(identifier)
    assert summary.scientific_name == "First source name"
    assert summary.selection_state == "unknown_order"
    assert {reference.provider for reference in summary.provider_references} == {"fixture", "other"}
    assert all(
        reference.qualification_state == "qualified" for reference in summary.provider_references
    )


def test_older_live_observation_cannot_replace_newer_source_and_import_time_never_ranks(catalog):
    identifier = catalog.publish(
        taxon(name="Fresh name"), retrieved_at=NOW, source_effective_at=NOW
    )
    catalog.publish(
        taxon(name="Old name"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW - timedelta(days=1),
    )
    assert catalog.resolve(identifier).scientific_name == "Fresh name"
    generation = catalog.begin_generation(
        replace(source("new snapshot"), snapshot_at=NOW + timedelta(days=2)),
        imported_at=NOW + timedelta(days=3),
    )
    catalog.stage(generation, [taxon(name="Newest snapshot")])
    catalog.validate_generation(generation)
    catalog.promote(generation)
    assert catalog.resolve(identifier).scientific_name == "Newest snapshot"


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "INVALID"},
        {"provider_id": ""},
        {"source_url": "http://example.test"},
        {"accepted_scientific_name": " "},
        {"supported_group": "invalid group"},
        {"taxonomic_status": "invented"},
        {"authorship": "x" * 257},
        {"synonyms": ("",)},
        {"synonyms": ("name",) * 65},
        {"parent_provider_id": ""},
    ],
)
def test_invalid_live_data_leaves_no_identity_or_revision(catalog, change):
    with pytest.raises(ValueError):
        catalog.publish(replace(taxon(), **change), retrieved_at=NOW)
    with catalog.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM taxa").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM taxonomy_changes").scalar_one() == 0


def test_bounded_promotion_and_unknown_ids_leave_state_unchanged(catalog):
    from uuid import uuid4

    assert catalog.resolve(uuid4()) is None
    with pytest.raises(ValueError):
        catalog.promote(uuid4())
    generation = stage(catalog, "bounded", [taxon()])
    with pytest.raises(ValueError, match="time bound"):
        catalog.promote(generation, max_seconds=0.000000001)
    assert catalog.active_generation() is None
    with pytest.raises(ValueError, match="staging"):
        catalog.stage(generation, [taxon()])
    with pytest.raises(ValueError):
        catalog.resolve_conflict(123, decided_by="owner", reason="No such conflict")


def test_staging_writer_during_validation_cannot_seal_a_changed_snapshot(catalog, monkeypatch):
    from contextlib import contextmanager
    from threading import Event

    reached = Event()
    resume = Event()
    original = catalog._read

    @contextmanager
    def hold_after_validation():
        with original() as connection:
            yield connection
        reached.set()
        assert resume.wait(5)

    generation = catalog.begin_generation(source("changing"), imported_at=NOW)
    catalog.stage(generation, [taxon()])
    monkeypatch.setattr(catalog, "_read", hold_after_validation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        validation = pool.submit(catalog.validate_generation, generation)
        assert reached.wait(5)
        catalog.stage(generation, [taxon("2", "Discovered while validating")])
        resume.set()
        with pytest.raises(ValueError, match="changed during validation"):
            validation.result()
    monkeypatch.setattr(catalog, "_read", original)
    catalog.validate_generation(generation)
    catalog.promote(generation)


def test_mapping_decisions_and_cleanup_preserve_conflict_audit(catalog):
    from uuid import uuid4

    identifier = catalog.publish(taxon(), retrieved_at=NOW)
    with pytest.raises(ValueError):
        catalog.map_identity(
            identifier, "other", "1", source_url="https://example.test", decided_by="", reason=""
        )
    with pytest.raises(ValueError):
        catalog.map_identity(
            uuid4(),
            "other",
            "1",
            source_url="https://example.test",
            decided_by="owner",
            reason="unknown identity",
        )
    generation = stage(catalog, "conflicts", [taxon("synonym", accepted_provider_id="1"), taxon()])
    conflict = catalog.conflicts()[0]
    catalog.resolve_conflict(
        conflict.conflict_id, decided_by="owner", reason="keep identities distinct"
    )
    catalog.cleanup(generation, retained_generations=set())
    with catalog.engine.connect() as connection:
        decision = connection.exec_driver_sql(
            "SELECT decided_by,reason FROM taxonomy_conflicts"
        ).one()
        assert tuple(decision) == ("owner", "keep identities distinct")
    assert catalog.resolve(identifier) is not None


def test_identical_observation_never_demotes_known_source_freshness(catalog):
    fresh = taxon(name="Fresh name", class_name="Freshclass")
    identifier = catalog.publish(fresh, retrieved_at=NOW, source_effective_at=NOW)
    generation = catalog.begin_generation(
        replace(source("Intervening"), snapshot_at=NOW - timedelta(days=1)), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Older name", class_name="Olderclass")])
    catalog.validate_generation(generation)
    catalog.promote(generation)
    catalog.publish(
        fresh, retrieved_at=NOW + timedelta(days=1), source_effective_at=NOW - timedelta(days=2)
    )
    assert catalog.resolve(identifier).scientific_name == "Fresh name"
    assert catalog.resolve(identifier).source_effective_at == NOW


def test_selected_overlay_classification_remains_searchable_after_staging_and_rejected_data(
    catalog,
):
    fresh = taxon(class_name="Freshclass")
    identifier = catalog.publish(fresh, retrieved_at=NOW, source_effective_at=NOW)
    generation = stage(catalog, "Older snapshot", [taxon(class_name="Olderclass")])
    assert catalog.search("Freshclass")[0].taxon_id == identifier
    catalog.promote(generation)
    catalog.publish(
        taxon(class_name="Rejectedclass"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW - timedelta(days=1),
    )
    assert ("class_name", "Freshclass") in catalog.resolve(identifier).classification
    assert catalog.search("Freshclass")[0].taxon_id == identifier


def test_group_search_uses_selected_mapping_before_limiting_results(catalog):
    identifier = catalog.publish(taxon(), retrieved_at=NOW, source_effective_at=NOW)
    catalog.publish(
        taxon(group="snake"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW + timedelta(days=1),
    )
    assert catalog.search("Rana", group="snake")[0].taxon_id == identifier
    catalog.publish(
        taxon(group="lizard"),
        retrieved_at=NOW + timedelta(days=2),
        source_effective_at=NOW + timedelta(days=2),
    )
    assert catalog.search("Rana", group="snake") == ()
    assert catalog.search("Rana", group="lizard")[0].taxon_id == identifier
    # Earlier matching but no-longer-selected groups must not consume the result limit.
    catalog.publish(taxon("z", "Zzz Rana", group="snake"), retrieved_at=NOW)
    assert catalog.search("Rana", group="snake", limit=1)[0].provider_id == "z"


def test_equal_dated_snapshot_and_overlay_require_an_explicit_decision(catalog):
    identifier = catalog.publish(
        taxon(name="Live equal"), retrieved_at=NOW, source_effective_at=NOW
    )
    generation = catalog.begin_generation(
        replace(source("Equal"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Snapshot equal")])
    catalog.validate_generation(generation)
    assert catalog.resolve(identifier).selection_state == "selected"
    assert catalog.conflicts()  # Private staging uncertainty blocks promotion, not live reads.
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(generation)
    assert catalog.active_generation() is None
    conflict = catalog.conflicts()[0]
    catalog.resolve_conflict(
        conflict.conflict_id, decided_by="owner", reason="retain live selection"
    )
    catalog.promote(generation)
    assert catalog.resolve(identifier).scientific_name == "Live equal"


def test_staging_another_snapshot_preserves_selected_name_group_classification_search(catalog):
    a = stage(catalog, "A reference only", [taxon(class_name="Oldclass")])
    catalog.promote(a)
    b = stage(
        catalog,
        "B qualified",
        [
            taxon(
                group="snake",
                class_name="Freshclass",
                preferred_common_name="Field frog",
                synonyms=("Historical frog",),
            )
        ],
    )
    catalog.promote(b)
    identifier = catalog.search("Rana")[0].taxon_id
    c = stage(catalog, "C staging", [taxon(group="lizard", class_name="Futureclass")])
    assert catalog.resolve(identifier).workflow_group == "snake"
    assert catalog.search("Rana", group="snake")[0].taxon_id == identifier
    assert catalog.search("Rana Freshclass")[0].taxon_id == identifier
    assert catalog.search("Field frog Freshclass")[0].taxon_id == identifier
    assert catalog.search("Historical frog", group="snake")[0].taxon_id == identifier
    catalog.promote(a)
    assert catalog.search("Rana Oldclass")[0].taxon_id == identifier
    assert catalog.search("Rana", group="snake") == ()
    catalog.cleanup(c, retained_generations={a, b})


def test_late_equal_clock_live_publication_blocks_already_staged_generation(catalog):
    generation = catalog.begin_generation(
        replace(source("Late live"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Snapshot equal")])
    catalog.validate_generation(generation)
    identifier = catalog.publish(
        taxon(name="Live equal"), retrieved_at=NOW, source_effective_at=NOW
    )
    assert catalog.resolve(identifier).selection_state == "selected"
    assert any(c.generation_id == generation for c in catalog.conflicts())
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(generation)


def test_renamed_identity_retains_alias_class_and_group_search_during_later_staging(catalog):
    a = stage(catalog, "A old label", [taxon(name="Oldrana temporaria", class_name="Oldclass")])
    catalog.promote(a)
    b = stage(
        catalog,
        "B new label",
        [taxon(name="Newrana temporaria", group="snake", class_name="Freshclass")],
    )
    catalog.promote(b)
    identifier = catalog.search("Oldrana", group="snake")[0].taxon_id
    stage(
        catalog,
        "C future label",
        [taxon(name="Futureana temporaria", group="lizard", class_name="Futureclass")],
    )
    assert catalog.resolve(identifier).scientific_name == "Newrana temporaria"
    assert catalog.search("Oldrana", group="snake")[0].taxon_id == identifier
    assert catalog.search("Oldrana Freshclass", group="snake")[0].taxon_id == identifier
    assert catalog.search("Oldrana", group="lizard") == ()


def test_staging_reservations_cannot_publish_directory_facts(catalog):
    from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    failed = catalog.begin_generation(source("Failed"), imported_at=NOW)
    catalog.stage(failed, [taxon(group="snake", parent_provider_id="absent")])
    with catalog.engine.connect() as connection:
        identifier = connection.execute(
            text("SELECT taxon_id FROM taxon_provider_mappings WHERE provider_id='1'")
        ).scalar_one()
    from uuid import UUID

    identifier = UUID(identifier)
    repository = SQLAlchemyTaxonRepository(catalog.engine)
    assert catalog.resolve(identifier) is None
    assert catalog.search("Rana") == ()
    assert repository.get(identifier, stale_after=NOW) is None
    assert repository.search("Rana", "snake", limit=10, stale_after=NOW) == ()
    with pytest.raises(ValueError, match="missing"):
        catalog.validate_generation(failed)
    catalog.cleanup(failed, retained_generations={a})
    assert repository.get(identifier, stale_after=NOW) is None
    good = stage(catalog, "Good", [taxon(name="Qualified rana", group="lizard")])
    assert catalog.resolve(identifier) is None
    catalog.promote(good)
    assert catalog.resolve(identifier).workflow_group == "lizard"
    catalog.promote(a)
    assert catalog.resolve(identifier).scientific_name == "Qualified rana"
    assert catalog.resolve(identifier).workflow_group == "lizard"


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
def test_direct_self_reference_cannot_validate_or_promote(catalog, relationship):
    generation = catalog.begin_generation(source("Self cycle"), imported_at=NOW)
    with pytest.raises(ValueError, match="cycle"):
        catalog.stage(generation, [taxon(**{relationship: "1"})])
    with pytest.raises(ValueError, match="Empty"):
        catalog.validate_generation(generation)
    with pytest.raises(ValueError, match="validated"):
        catalog.promote(generation)


def test_live_discovery_can_qualify_a_staging_reservation_without_promoting_it(catalog):
    generation = catalog.begin_generation(source("Staging"), imported_at=NOW)
    catalog.stage(generation, [taxon(group="snake", parent_provider_id="absent")])
    identifier = catalog.publish(taxon(name="Live qualified", group="lizard"), retrieved_at=NOW)
    assert catalog.active_generation() is None
    assert catalog.resolve(identifier).scientific_name == "Live qualified"
    assert catalog.search("Live", group="lizard")[0].taxon_id == identifier
    assert catalog.search("Live", group="snake") == ()
    catalog.cleanup(generation, retained_generations=set())
    assert catalog.resolve(identifier).workflow_group == "lizard"


def test_first_promotion_preserves_qualified_fallback_provenance(catalog):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    failed = catalog.begin_generation(
        replace(source("Failed"), retrieved_at=NOW - timedelta(days=20)), imported_at=NOW
    )
    catalog.stage(failed, [replace(taxon(), source_url="https://example.test/FAILED")])
    good = stage(
        catalog, "Good", [replace(taxon(name="Qualified"), source_url="https://example.test/GOOD")]
    )
    catalog.promote(good)
    identifier = catalog.search("Qualified")[0].taxon_id
    catalog.promote(a)
    catalog.cleanup(good, retained_generations={a})
    summary = catalog.resolve(identifier)
    assert summary.source_url == "https://example.test/GOOD"
    assert summary.retrieved_at == NOW
    assert summary.source_effective_at == NOW - timedelta(days=10)


def test_reviewed_guide_import_rejects_staging_only_identity(catalog):
    from snaketracker.application.care_guides import GuideBundle
    from snaketracker.infrastructure.taxonomy.care_guides import (
        CareGuideImportError,
        SQLAlchemyCareGuideRepository,
    )

    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    bundle = bundle.model_copy(
        update={"guides": tuple(g for g in bundle.guides if g.scientific_name == "Python regius")}
    )
    generation = catalog.begin_generation(source("Unvalidated"), imported_at=NOW)
    catalog.stage(
        generation, [taxon(name="Python regius", group="snake", parent_provider_id="absent")]
    )
    with pytest.raises(CareGuideImportError, match="exactly one"):
        SQLAlchemyCareGuideRepository(catalog.engine).import_bundle(bundle)


def test_rollback_keeps_newer_qualified_fallback_over_older_overlay(catalog):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    b = catalog.begin_generation(replace(source("B"), snapshot_at=NOW), imported_at=NOW)
    catalog.stage(b, [taxon(name="Fresh name")])
    catalog.validate_generation(b)
    catalog.promote(b)
    identifier = catalog.publish(
        taxon(name="Older overlay"), retrieved_at=NOW, source_effective_at=NOW - timedelta(days=1)
    )
    assert catalog.resolve(identifier).scientific_name == "Fresh name"
    catalog.promote(a)
    catalog.cleanup(b, retained_generations={a})
    assert catalog.resolve(identifier).scientific_name == "Fresh name"
    assert catalog.resolve(identifier).source_effective_at == NOW


def test_undated_disagreement_retains_selected_overlay_until_decision(catalog):
    identifier = catalog.publish(taxon(name="Selected name", group="snake"), retrieved_at=NOW)
    catalog.publish(
        taxon(name="Unordered name", group="lizard"), retrieved_at=NOW + timedelta(days=1)
    )
    summary = catalog.resolve(identifier)
    assert summary.scientific_name == "Selected name"
    assert summary.workflow_group == "snake"
    assert summary.selection_state == "unknown_order"
    assert catalog.search("Unordered") == ()
    assert catalog.conflicts()


def test_existing_identity_staging_labels_remain_private_even_after_failed_cleanup(catalog):
    from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

    identifier = catalog.publish(
        taxon(name="Selected name", alternative_common_names=("Known common",)), retrieved_at=NOW
    )
    with catalog.engine.connect() as connection:
        before = connection.execute(text("SELECT * FROM taxon_names ORDER BY name,name_kind")).all()
    generation = catalog.begin_generation(source("Bad labels"), imported_at=NOW)
    catalog.stage(
        generation,
        [
            taxon(
                name="Unpublished scientific",
                alternative_common_names=("Unpublished common",),
                class_name="Unpublishedclass",
                parent_provider_id="absent",
            )
        ],
    )
    with catalog.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT * FROM taxon_names ORDER BY name,name_kind")).all()
            == before
        )
    assert catalog.search("Unpublished") == ()
    assert SQLAlchemyTaxonRepository(catalog.engine).get(
        identifier, stale_after=NOW
    ).alternative_common_names == ("Known common",)
    with pytest.raises(ValueError, match="missing"):
        catalog.validate_generation(generation)
    catalog.cleanup(generation, retained_generations=set())
    assert catalog.search("Unpublished") == ()


def test_interrupted_cleanup_retires_generation_and_resumes_bounded_compaction(
    catalog, monkeypatch
):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    b = catalog.begin_generation(source("B"), imported_at=NOW)
    records = [
        taxon(
            str(index), f"Cleanup reference {index:04d}", synonyms=(f"Previous alias {index:04d}",)
        )
        for index in range(501)
    ]
    catalog.stage(b, records[:500])
    catalog.stage(b, records[500:])
    catalog.validate_generation(b)
    catalog.promote(b)
    catalog.promote(a)
    original = catalog._labels
    count = 0

    def interrupt(connection, identifier, candidate):
        nonlocal count
        count += 1
        if count == 501:
            raise RuntimeError("Synthetic interruption after committed first batch")
        original(connection, identifier, candidate)

    monkeypatch.setattr(catalog, "_labels", interrupt)
    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        catalog.cleanup(b, retained_generations={a})
    with catalog.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM taxonomy_facts WHERE generation_id=:g"), {"g": str(b)}
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT state FROM taxonomy_generations WHERE generation_id=:g"), {"g": str(b)}
            ).scalar_one()
            == "retiring"
        )
    with pytest.raises(ValueError, match="validated"):
        catalog.promote(b)
    assert len(catalog.search("Cleanup reference", limit=20)) == 20
    monkeypatch.setattr(catalog, "_labels", original)
    catalog.cleanup(b, retained_generations={a})
    summary = catalog.search("Previous alias 0500")[0]
    assert summary.scientific_name == "Cleanup reference 0500"
    assert summary.synonyms == ("Previous alias 0500",)
    assert catalog.active_generation() == a


def test_active_generation_requires_its_atomic_publication_receipt(catalog):
    from snaketracker.bootstrap.compatibility import inspect_startup_compatibility

    generation = stage(catalog, "A", [taxon()])
    catalog.promote(generation)
    with catalog.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM taxonomy_generation_publications")
    assert (
        inspect_startup_compatibility(catalog.engine).reason_code
        == "taxonomy_reference_incompatible"
    )


def test_foreign_overlay_cannot_replace_generation_origin(catalog):
    generation = stage(
        catalog, "Origin", [taxon(name="Original selected", authorship="Original author")]
    )
    catalog.promote(generation)
    identifier = catalog.search("Original")[0].taxon_id
    catalog.map_identity(
        identifier,
        "foreign",
        "foreign-1",
        source_url="https://example.test/foreign",
        decided_by="Operator",
        reason="Qualified cross-provider identity",
    )
    catalog.publish(
        replace(taxon("foreign-1", "Foreign selected"), provider="foreign"), retrieved_at=NOW
    )
    assert catalog.resolve(identifier).scientific_name == "Original selected"
    assert catalog.resolve(identifier).selection_state == "unknown_order"


def test_resolved_equal_clock_conflict_clears_selection_uncertainty(catalog):
    identifier = catalog.publish(
        taxon(name="Live selected"), retrieved_at=NOW, source_effective_at=source("B").snapshot_at
    )
    generation = stage(catalog, "B", [taxon(name="Snapshot equal")])
    for conflict in catalog.conflicts():
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain current live selection"
        )
    catalog.promote(generation)
    assert catalog.resolve(identifier).scientific_name == "Live selected"
    assert catalog.resolve(identifier).selection_state == "selected"


def test_directory_authorship_follows_selected_generation(catalog):
    from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

    a = stage(catalog, "A", [taxon(name="Old species", authorship="Old author")])
    catalog.promote(a)
    identifier = catalog.search("Old")[0].taxon_id
    b = stage(catalog, "B", [taxon(name="New species", authorship="New author")])
    catalog.promote(b)
    record = SQLAlchemyTaxonRepository(catalog.engine).get(identifier, stale_after=NOW)
    assert record.accepted_scientific_name == "New species"
    assert record.authorship == "New author"


def test_guide_import_matches_selected_name_and_group_instead_of_fallback(catalog):
    from snaketracker.application.care_guides import GuideBundle
    from snaketracker.infrastructure.taxonomy.care_guides import (
        CareGuideImportError,
        SQLAlchemyCareGuideRepository,
    )

    catalog.publish(
        taxon(name="Legacy python", group="lizard"),
        retrieved_at=NOW,
        source_effective_at=NOW - timedelta(days=20),
    )
    generation = stage(catalog, "Current", [taxon(name="Python regius", group="snake")])
    catalog.promote(generation)
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    guide = next(g for g in bundle.guides if g.scientific_name == "Python regius")
    repository = SQLAlchemyCareGuideRepository(catalog.engine)
    assert repository.import_bundle(GuideBundle(format_version=1, guides=(guide,))) == (1, 0)
    stale = guide.model_copy(
        update={
            "scientific_name": "Legacy python",
            "biological_group": type(guide.biological_group)("lizard"),
        }
    )
    with pytest.raises(CareGuideImportError, match="exactly one"):
        repository.import_bundle(GuideBundle(format_version=1, guides=(stale,)))


@pytest.mark.parametrize("effective", [None, NOW])
def test_first_live_disagreement_cannot_replace_selected_generation_without_order(
    catalog, effective
):
    generation = catalog.begin_generation(
        replace(source("Known baseline"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Selected baseline")])
    catalog.validate_generation(generation)
    catalog.promote(generation)
    identifier = catalog.publish(
        taxon(name="Unordered replacement"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=effective,
    )
    assert catalog.resolve(identifier).scientific_name == "Selected baseline"
    assert catalog.resolve(identifier).selection_state == "unknown_order"
    assert catalog.search("Unordered") == ()


def test_reconciliation_bound_excludes_staged_population_but_counts_live_delta(catalog):
    generation = stage(
        catalog, "Private population", [taxon(str(i), f"Staged species {i}") for i in range(5)]
    )
    catalog.promote(generation, max_revisions=0)
    next_generation = stage(
        catalog, "Next", [taxon(str(i), f"Staged species {i}") for i in range(5)]
    )
    catalog.publish(taxon("live-delta", "Concurrent discovery"), retrieved_at=NOW)
    with pytest.raises(ValueError, match="identity bound"):
        catalog.promote(next_generation, max_revisions=0)
    catalog.promote(next_generation, max_revisions=1)
    with catalog.engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT DISTINCT taxon_id FROM taxonomy_changes "
            "WHERE revision>0 AND revision<=30000 "
            "AND kind NOT IN ('snapshot_identity_reserved','snapshot_labels') LIMIT 10001"
        ).all()
        assert any("ix_taxonomy_public_changes" in row[3] for row in plan)


@pytest.mark.parametrize("snapshot,live", [(None, NOW), (NOW, None), (None, None)])
def test_incomparable_staged_facts_have_resolvable_private_conflicts(catalog, snapshot, live):
    identifier = catalog.publish(
        taxon(name="Live chosen"), retrieved_at=NOW, source_effective_at=live
    )
    generation = catalog.begin_generation(
        replace(source("Incomparable"), snapshot_at=snapshot), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Staged different")])
    catalog.validate_generation(generation)
    conflicts = [c for c in catalog.conflicts() if c.generation_id == generation]
    assert len(conflicts) == 1 and conflicts[0].kind == "unknown_order"
    assert catalog.resolve(identifier).selection_state == "selected"
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(generation)
    catalog.resolve_conflict(
        conflicts[0].conflict_id, decided_by="Owner", reason="Retain current live facts"
    )
    catalog.promote(generation)
    assert catalog.resolve(identifier).scientific_name == "Live chosen"
    assert catalog.resolve(identifier).selection_state == "selected"


@pytest.mark.parametrize("rollback", [False, True])
def test_foreign_overlay_order_has_durable_resolvable_decision(catalog, rollback):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    b = stage(catalog, "B", [taxon(name="Chosen origin")])
    catalog.promote(b)
    identifier = catalog.search("Chosen")[0].taxon_id
    if rollback:
        catalog.promote(a)
    catalog.map_identity(
        identifier,
        "foreign",
        "other",
        source_url="https://example.test/other",
        decided_by="Owner",
        reason="Qualified identity",
    )
    catalog.publish(replace(taxon("other", "Foreign facts"), provider="foreign"), retrieved_at=NOW)
    conflicts = [c for c in catalog.conflicts() if c.kind == "cross_provider_order"]
    assert conflicts
    assert catalog.resolve(identifier).scientific_name == "Chosen origin"
    assert catalog.resolve(identifier).selection_state == "unknown_order"
    for conflict in conflicts:
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain origin facts"
        )
    assert catalog.resolve(identifier).selection_state == "selected"


def test_published_conflict_evidence_survives_cleanup_without_tainting_active_selection(catalog):
    a = stage(catalog, "A", [taxon(name="Original selected")])
    catalog.promote(a)
    b = catalog.begin_generation(replace(source("B"), snapshot_at=NOW), imported_at=NOW)
    catalog.stage(b, [taxon(name="Published B")])
    catalog.validate_generation(b)
    catalog.promote(b)
    catalog.promote(a)
    identifier = catalog.publish(
        taxon(name="Live equal B"), retrieved_at=NOW, source_effective_at=NOW
    )
    conflicts = [c for c in catalog.conflicts() if c.generation_id == b]
    assert conflicts and catalog.resolve(identifier).selection_state == "selected"
    assert catalog.resolve(identifier).scientific_name == "Live equal B"
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(b)
    catalog.cleanup(b, retained_generations={a})
    assert [c for c in catalog.conflicts() if c.generation_id == b] == conflicts
    assert catalog.resolve(identifier).selection_state == "selected"
    for conflict in conflicts:
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain selected live facts"
        )
    assert catalog.resolve(identifier).selection_state == "selected"


@pytest.mark.parametrize("snapshot,live", [(None, NOW), (NOW, None), (None, None)])
def test_live_after_staging_records_incomparable_generation_conflict(catalog, snapshot, live):
    a = stage(catalog, "A", [taxon(name="Original selected")])
    catalog.promote(a)
    b = catalog.begin_generation(replace(source("B"), snapshot_at=snapshot), imported_at=NOW)
    catalog.stage(b, [taxon(name="Staged uncertain")])
    catalog.validate_generation(b)
    catalog.publish(taxon(name="Later live"), retrieved_at=NOW, source_effective_at=live)
    assert any(c.generation_id == b and c.kind == "unknown_order" for c in catalog.conflicts())
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(b)


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_reconciliation_budget_cannot_disable_the_guard(catalog, seconds):
    from uuid import uuid4

    with pytest.raises(ValueError, match="Invalid reconciliation bound"):
        catalog.promote(uuid4(), max_seconds=seconds)


def test_group_search_bounds_candidate_resolution_and_reports_refinement(catalog, monkeypatch):
    generation = stage(
        catalog,
        "Broad",
        [taxon(str(i), f"Broad species {i}") for i in range(4)]
        + [taxon("z", "Broad target", group="snake")],
    )
    catalog.promote(generation)
    bounded = LocalTaxonomyCatalog(catalog.engine, search_max_candidates=2)
    calls = 0
    original = bounded._selected

    def counted(connection, identifier):
        nonlocal calls
        calls += 1
        return original(connection, identifier)

    monkeypatch.setattr(bounded, "_selected", counted)
    with pytest.raises(ValueError, match=r"[Rr]efine"):
        bounded.search("Broad", group="snake")
    assert calls <= 2
    assert bounded.search("Broad target", group="snake")[0].provider_id == "z"


def test_search_sql_deadline_interrupts_work_and_resets_connection(catalog, monkeypatch):
    from types import SimpleNamespace

    from snaketracker.application.local_taxonomy import TaxonomySearchLimitError
    from snaketracker.infrastructure.taxonomy import catalog as module

    identifier = catalog.publish(taxon(), retrieved_at=NOW)
    original = module.execute
    ticks = 0

    def clock():
        nonlocal ticks
        ticks += 2
        return ticks

    def expensive(connection, sql, **parameters):
        if sql.startswith("WITH matches"):
            return original(
                connection,
                "WITH RECURSIVE work(x) AS (VALUES(1) UNION ALL "
                "SELECT x+1 FROM work WHERE x<100000) SELECT x FROM work",
            )
        return original(connection, sql, **parameters)

    with monkeypatch.context() as patch:
        patch.setattr(module, "time", SimpleNamespace(monotonic=clock))
        patch.setattr(module, "execute", expensive)
        with pytest.raises(TaxonomySearchLimitError, match="Refine"):
            catalog.search("Rana")
    assert catalog.search("Rana")[0].taxon_id == identifier


@pytest.mark.parametrize("effective", [None, NOW, NOW + timedelta(days=1)])
def test_live_observation_compares_selected_snapshot_even_with_older_overlay(catalog, effective):
    identifier = catalog.publish(
        taxon(name="Older overlay", group="lizard"),
        retrieved_at=NOW,
        source_effective_at=NOW - timedelta(days=10),
    )
    generation = catalog.begin_generation(
        replace(source("Selected snapshot"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(generation, [taxon(name="Selected snapshot", group="snake")])
    catalog.validate_generation(generation)
    catalog.promote(generation)
    assert catalog.resolve(identifier).scientific_name == "Selected snapshot"
    catalog.publish(
        taxon(name="Incoming observation", group="lizard"),
        retrieved_at=NOW + timedelta(days=2),
        source_effective_at=effective,
    )
    selected = catalog.resolve(identifier)
    if effective and effective > NOW:
        assert selected.scientific_name == "Incoming observation"
        assert selected.workflow_group == "lizard"
        assert selected.selection_state == "selected"
    else:
        assert selected.scientific_name == "Selected snapshot"
        assert selected.workflow_group == "snake"
        assert selected.selection_state == "unknown_order"


@pytest.mark.parametrize("origin", ["overlay", "snapshot", "snapshot_with_old_overlay"])
def test_foreign_generation_retains_selected_origin_after_conflict_decision(catalog, origin):
    if origin == "overlay":
        identifier = catalog.publish(
            taxon(name="Preferred current", group="snake"), retrieved_at=NOW
        )
    else:
        a = stage(catalog, "Original snapshot", [taxon(name="Preferred old", group="lizard")])
        catalog.promote(a)
        identifier = catalog.search("Preferred")[0].taxon_id
        if origin == "snapshot_with_old_overlay":
            catalog.publish(
                taxon(name="Preferred old", group="lizard"),
                retrieved_at=NOW,
                source_effective_at=NOW - timedelta(days=10),
            )
        b = catalog.begin_generation(
            replace(source("New preferred"), snapshot_at=NOW), imported_at=NOW
        )
        catalog.stage(b, [taxon(name="Preferred current", group="snake")])
        catalog.validate_generation(b)
        catalog.promote(b)
    catalog.map_identity(
        identifier,
        "foreign",
        "other",
        source_url="https://example.test/other",
        decided_by="Owner",
        reason="Qualified identity",
    )
    foreign = catalog.begin_generation(
        replace(source("Foreign"), provider="foreign"), imported_at=NOW
    )
    catalog.stage(
        foreign,
        [replace(taxon("other", "Foreign replacement", group="lizard"), provider="foreign")],
    )
    catalog.validate_generation(foreign)
    conflicts = [c for c in catalog.conflicts() if c.kind == "cross_provider_order"]
    assert conflicts
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(foreign)
    for conflict in conflicts:
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain preferred origin"
        )
    catalog.promote(foreign)
    selected = catalog.resolve(identifier)
    assert selected.scientific_name == "Preferred current"
    assert selected.workflow_group == "snake"
    assert selected.provider == "fixture"
    assert selected.selection_state == "selected"
    if origin != "overlay":
        catalog.cleanup(b, retained_generations={foreign})
        assert catalog.resolve(identifier).scientific_name == "Preferred current"


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
def test_direct_live_relationship_cycles_are_rejected_before_reservation(catalog, relationship):
    with pytest.raises(ValueError, match=r"self|cycle"):
        catalog.publish(taxon(**{relationship: "1"}), retrieved_at=NOW)
    assert catalog.search("Rana") == ()
    with catalog.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM taxa")).scalar_one() == 0


def test_new_comparison_reopens_previously_resolved_payload_conflict(catalog):
    catalog.publish(taxon(name="Selected A"), retrieved_at=NOW, source_effective_at=NOW)
    disputed = taxon(name="Disputed X")
    identifier = catalog.publish(disputed, retrieved_at=NOW, source_effective_at=NOW)
    first = catalog.conflicts()[0]
    catalog.resolve_conflict(first.conflict_id, decided_by="Owner", reason="Retain A")
    catalog.publish(
        taxon(name="Selected B"), retrieved_at=NOW, source_effective_at=NOW + timedelta(days=1)
    )
    catalog.publish(
        disputed, retrieved_at=NOW + timedelta(days=2), source_effective_at=NOW + timedelta(days=1)
    )
    current = catalog.conflicts()
    assert len(current) == 1
    assert current[0].conflict_id != first.conflict_id
    assert catalog.resolve(identifier).scientific_name == "Selected B"
    assert catalog.resolve(identifier).selection_state == "unknown_order"


def test_repeated_identical_comparison_preserves_content_bound_conflict_decision(catalog):
    identifier = catalog.publish(
        taxon(name="Selected A"), retrieved_at=NOW, source_effective_at=NOW
    )
    disputed = taxon(name="Disputed X")
    catalog.publish(disputed, retrieved_at=NOW, source_effective_at=NOW)
    for conflict in catalog.conflicts():
        catalog.resolve_conflict(conflict.conflict_id, decided_by="Owner", reason="Retain A")
    catalog.publish(disputed, retrieved_at=NOW + timedelta(days=1), source_effective_at=NOW)
    assert catalog.conflicts() == ()
    assert catalog.resolve(identifier).scientific_name == "Selected A"
    assert catalog.resolve(identifier).selection_state == "selected"


def test_cleanup_rejects_unknown_generation_without_changing_current_data(catalog):
    from uuid import uuid4

    current = stage(catalog, "Current", [taxon()])
    catalog.promote(current)
    with pytest.raises(ValueError, match="Unknown"):
        catalog.cleanup(uuid4(), retained_generations={current})
    assert catalog.active_generation() == current
    assert catalog.search("Rana")[0].scientific_name == "Rana temporaria"


def test_newer_live_overlay_is_retained_beneath_snapshot_for_later_rollback(catalog):
    identifier = catalog.publish(
        taxon(name="January first"), retrieved_at=NOW, source_effective_at=NOW - timedelta(days=10)
    )
    a = stage(catalog, "Rollback target", [taxon("root", "Animalia")])
    catalog.promote(a)
    b = catalog.begin_generation(replace(source("New snapshot"), snapshot_at=NOW), imported_at=NOW)
    catalog.stage(b, [taxon(name="Snapshot latest")])
    catalog.validate_generation(b)
    catalog.promote(b)
    catalog.publish(
        taxon(name="Intermediate live"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW - timedelta(days=5),
    )
    assert catalog.resolve(identifier).scientific_name == "Snapshot latest"
    catalog.publish(
        taxon(name="Even older live"),
        retrieved_at=NOW + timedelta(days=2),
        source_effective_at=NOW - timedelta(days=11),
    )
    catalog.promote(a)
    catalog.cleanup(b, retained_generations={a})
    assert catalog.resolve(identifier).scientific_name == "Intermediate live"
    assert catalog.resolve(identifier).source_effective_at == NOW - timedelta(days=5)


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
@pytest.mark.parametrize("length", [2, 3])
def test_live_relationships_reject_indirect_cycles_before_publication(
    catalog, relationship, length
):
    for index in range(1, length):
        catalog.publish(
            taxon(str(index), f"Species {index}", **{relationship: str(index + 1)}),
            retrieved_at=NOW,
        )
    with pytest.raises(ValueError, match="cycle"):
        catalog.publish(
            taxon(str(length), "Cycle closing taxon", **{relationship: "1"}), retrieved_at=NOW
        )
    assert catalog.search("Cycle closing") == ()
    with catalog.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM taxon_provider_mappings WHERE provider_id=:id"),
                {"id": str(length)},
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
def test_concurrent_live_observations_cannot_close_relationship_cycle(catalog, relationship):
    def publish(index):
        try:
            catalog.publish(
                taxon(str(index), f"Concurrent species {index}", **{relationship: str(3 - index)}),
                retrieved_at=NOW,
            )
            return "published"
        except ValueError as error:
            assert "cycle" in str(error)
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, [1, 2]))
    assert sorted(outcomes) == ["published", "rejected"]
    assert len(catalog.search("Concurrent")) == 1


def test_local_search_intersects_every_word_within_accepted_query_length(catalog):
    prefix = "aa bb cc dd ee ff gg hh ii jj kk ll"
    catalog.publish(taxon("1", prefix), retrieved_at=NOW)
    catalog.publish(taxon("2", prefix + " zz"), retrieved_at=NOW)
    assert catalog.search(prefix + " missing") == ()
    assert [item.provider_id for item in catalog.search(prefix + " zz")] == ["2"]


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
def test_live_cycle_cannot_hide_behind_an_alias_of_the_same_permanent_uuid(catalog, relationship):
    identifier = catalog.publish(taxon(), retrieved_at=NOW, source_effective_at=NOW)
    catalog.map_identity(
        identifier,
        "fixture",
        "alias",
        source_url="https://example.test/alias",
        decided_by="Owner",
        reason="Qualified synonymous provider identity",
    )
    with pytest.raises(ValueError, match="cycle"):
        catalog.publish(
            taxon(**{relationship: "alias"}),
            retrieved_at=NOW + timedelta(days=1),
            source_effective_at=NOW + timedelta(days=1),
        )
    assert catalog.resolve(identifier).source_effective_at == NOW
    with catalog.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT json_extract(payload,:field) FROM taxonomy_overlay WHERE taxon_id=:id"
                ),
                {"field": "$." + relationship, "id": str(identifier)},
            ).scalar_one()
            is None
        )


@pytest.mark.parametrize("facts", ["overlay", "snapshot"])
def test_secondary_provider_relationship_cycles_use_its_own_qualified_facts(catalog, facts):
    identifiers = {}
    for key in ("a", "b"):
        identifiers[key] = catalog.publish(taxon(key, f"Origin {key}"), retrieved_at=NOW)
        catalog.map_identity(
            identifiers[key],
            "foreign",
            key,
            source_url=f"https://example.test/foreign/{key}",
            decided_by="Owner",
            reason="Qualified identity",
        )
    first = replace(taxon("a", "Foreign a", parent_provider_id="b"), provider="foreign")
    if facts == "overlay":
        catalog.publish(first, retrieved_at=NOW)
    else:
        generation = catalog.begin_generation(
            replace(source("Foreign relationships"), provider="foreign"), imported_at=NOW
        )
        catalog.stage(generation, [first, replace(taxon("b", "Foreign b"), provider="foreign")])
        catalog.validate_generation(generation)
        for conflict in catalog.conflicts():
            catalog.resolve_conflict(
                conflict.conflict_id, decided_by="Owner", reason="Retain origin"
            )
        catalog.promote(generation)
    with pytest.raises(ValueError, match="cycle"):
        catalog.publish(
            replace(
                taxon("b", "Closing foreign cycle", parent_provider_id="a"), provider="foreign"
            ),
            retrieved_at=NOW,
        )
    assert catalog.resolve(identifiers["b"]).scientific_name == "Origin b"


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
def test_new_identity_alias_mapping_cannot_close_an_existing_live_cycle(catalog, relationship):
    identifier = catalog.publish(taxon(**{relationship: "alias"}), retrieved_at=NOW)
    with pytest.raises(ValueError, match="cycle"):
        catalog.map_identity(
            identifier,
            "fixture",
            "alias",
            source_url="https://example.test/alias",
            decided_by="Owner",
            reason="Proposed alias would close cycle",
        )
    assert [
        reference.provider_id for reference in catalog.resolve(identifier).provider_references
    ] == ["1"]


@pytest.mark.parametrize("relationship", ["parent_provider_id", "accepted_provider_id"])
@pytest.mark.parametrize("state", ["hidden_overlay", "first_fallback"])
def test_alias_mapping_checks_retained_relationships_beneath_newer_facts(
    catalog, relationship, state
):
    identifier = catalog.publish(
        taxon(**{relationship: "alias"}), retrieved_at=NOW, source_effective_at=NOW
    )
    for conflict in catalog.conflicts():
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain partial reference"
        )
    a = stage(catalog, "Rollback without this taxon", [taxon("root", "Animalia")])
    catalog.promote(a)
    if state == "hidden_overlay":
        b = catalog.begin_generation(
            replace(source("Newer snapshot"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
        )
        catalog.stage(b, [taxon()])
        catalog.validate_generation(b)
        catalog.promote(b)
    else:
        catalog.publish(
            taxon(),
            retrieved_at=NOW + timedelta(days=1),
            source_effective_at=NOW + timedelta(days=1),
        )

    def qualify_alias():
        catalog.map_identity(
            identifier,
            "fixture",
            "alias",
            source_url="https://example.test/alias",
            decided_by="Owner",
            reason="Proposed identity alias",
        )

    if state == "hidden_overlay":
        with pytest.raises(ValueError, match="cycle"):
            qualify_alias()
        expected = {"1"}
    else:
        # The durable newer observation clears the old fallback edge in every
        # selectable view; rollback cannot resurrect that obsolete edge.
        qualify_alias()
        expected = {"1", "alias"}
    catalog.promote(a)
    assert {
        reference.provider_id for reference in catalog.resolve(identifier).provider_references
    } == expected


def test_mapping_alias_checks_hidden_multi_record_live_chain(catalog):
    identifier = catalog.publish(
        taxon("1", "First", parent_provider_id="2"), retrieved_at=NOW, source_effective_at=NOW
    )
    catalog.publish(
        taxon("2", "Second", parent_provider_id="alias"), retrieved_at=NOW, source_effective_at=NOW
    )
    b = catalog.begin_generation(
        replace(source("Hiding both edges"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
    )
    catalog.stage(b, [taxon("1", "First"), taxon("2", "Second")])
    catalog.validate_generation(b)
    catalog.promote(b)
    with pytest.raises(ValueError, match="cycle"):
        catalog.map_identity(
            identifier,
            "fixture",
            "alias",
            source_url="https://example.test/alias",
            decided_by="Owner",
            reason="Proposed identity alias",
        )


def test_live_cycle_guard_covers_the_rollback_overlay_view(catalog):
    catalog.publish(
        taxon("a", "First", parent_provider_id="b"), retrieved_at=NOW, source_effective_at=NOW
    )
    catalog.publish(taxon("b", "Second"), retrieved_at=NOW, source_effective_at=NOW)
    g = catalog.begin_generation(
        replace(source("Hiding old live edge"), snapshot_at=NOW + timedelta(days=1)),
        imported_at=NOW,
    )
    catalog.stage(g, [taxon("a", "First"), taxon("b", "Second")])
    catalog.validate_generation(g)
    catalog.promote(g)
    with pytest.raises(ValueError, match="cycle"):
        catalog.publish(
            taxon("b", "Second", parent_provider_id="a"),
            retrieved_at=NOW + timedelta(days=2),
            source_effective_at=NOW + timedelta(days=2),
        )


def test_generation_validation_rejects_cycle_with_newer_durable_overlay(catalog):
    catalog.publish(taxon("a", "First"), retrieved_at=NOW, source_effective_at=NOW)
    catalog.publish(
        taxon("b", "Second", parent_provider_id="a"),
        retrieved_at=NOW,
        source_effective_at=NOW + timedelta(days=2),
    )
    g = catalog.begin_generation(
        replace(source("Overlay union"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
    )
    catalog.stage(g, [taxon("a", "First", parent_provider_id="b"), taxon("b", "Second")])
    with pytest.raises(ValueError, match="cycle"):
        catalog.validate_generation(g)
    assert catalog.active_generation() is None


def test_late_live_change_cannot_introduce_cycle_at_generation_promotion(catalog):
    catalog.publish(taxon("a", "First"), retrieved_at=NOW, source_effective_at=NOW)
    catalog.publish(taxon("b", "Second"), retrieved_at=NOW, source_effective_at=NOW)
    g = catalog.begin_generation(
        replace(source("Late cycle"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
    )
    catalog.stage(g, [taxon("a", "First", parent_provider_id="b"), taxon("b", "Second")])
    catalog.validate_generation(g)
    catalog.publish(
        taxon("b", "Second", parent_provider_id="a"),
        retrieved_at=NOW + timedelta(days=2),
        source_effective_at=NOW + timedelta(days=2),
    )
    with pytest.raises(ValueError, match="cycle"):
        catalog.promote(g)
    assert catalog.active_generation() is None
    catalog.publish(
        taxon("a", "First"),
        retrieved_at=NOW + timedelta(days=2),
        source_effective_at=NOW + timedelta(days=2),
    )
    catalog.promote(g)
    assert catalog.active_generation() == g


def test_newer_live_reparenting_does_not_mix_in_unselected_historical_edges(catalog):
    catalog.publish(
        taxon("a", "First", parent_provider_id="b"), retrieved_at=NOW, source_effective_at=NOW
    )
    catalog.publish(taxon("b", "Second"), retrieved_at=NOW, source_effective_at=NOW)
    g = catalog.begin_generation(
        replace(source("Historical direction"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(g, [taxon("a", "First", parent_provider_id="b"), taxon("b", "Second")])
    catalog.validate_generation(g)
    catalog.promote(g)
    catalog.publish(
        taxon("a", "First"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW + timedelta(days=1),
    )
    identifier = catalog.publish(
        taxon("b", "Second", parent_provider_id="a"),
        retrieved_at=NOW + timedelta(days=1),
        source_effective_at=NOW + timedelta(days=1),
    )
    assert [item.scientific_name for item in catalog.resolve(identifier).ancestry] == ["First"]


def test_new_reference_publication_must_leave_fallback_graph_acyclic(catalog):
    catalog.publish(
        taxon("a", "First", parent_provider_id="b"), retrieved_at=NOW, source_effective_at=NOW
    )
    g = catalog.begin_generation(
        replace(source("New catalog fallback"), snapshot_at=NOW + timedelta(days=1)),
        imported_at=NOW,
    )
    catalog.stage(g, [taxon("a", "First"), taxon("b", "Second", parent_provider_id="a")])
    with pytest.raises(ValueError, match="cycle"):
        catalog.validate_generation(g)
    assert catalog.active_generation() is None
    assert catalog.search("Second") == ()


def test_other_generation_first_publication_is_a_qualified_reconciliation_delta(catalog):
    target = stage(catalog, "Waiting", [taxon("target", "Waiting reference")])
    other = stage(catalog, "First publication", [taxon("other", "Other reference")])
    catalog.promote(other, max_revisions=0)
    with pytest.raises(ValueError, match="identity bound"):
        catalog.promote(target, max_revisions=0)
    catalog.promote(target, max_revisions=1)
    assert catalog.active_generation() == target
    assert catalog.search("Other")[0].provider_id == "other"


def test_alias_mapping_does_not_mix_obsolete_edges_across_coherent_views(catalog):
    a = stage(
        catalog,
        "Historical first direction",
        [taxon("x", "First", parent_provider_id="y"), taxon("y", "Second")],
    )
    catalog.promote(a)
    b = catalog.begin_generation(
        replace(source("Historical reverse direction"), snapshot_at=NOW - timedelta(days=5)),
        imported_at=NOW,
    )
    catalog.stage(b, [taxon("x", "First"), taxon("y", "Second", parent_provider_id="x")])
    catalog.validate_generation(b)
    catalog.promote(b)
    first = catalog.publish(taxon("x", "First"), retrieved_at=NOW, source_effective_at=NOW)
    second = catalog.publish(
        taxon("y", "Second", parent_provider_id="alias"),
        retrieved_at=NOW,
        source_effective_at=NOW,
    )
    catalog.map_identity(
        first,
        "fixture",
        "alias",
        source_url="https://example.test/alias",
        decided_by="Owner",
        reason="Qualified alias with acyclic retained views",
    )
    for generation in (a, b):
        catalog.promote(generation)
        assert [item.taxon_id for item in catalog.resolve(second).ancestry] == [first]
        assert {r.provider_id for r in catalog.resolve(first).provider_references} == {"x", "alias"}


@pytest.mark.parametrize("parent_scope", ["overlay", "snapshot"])
def test_ancestry_keeps_the_child_relationship_namespace(catalog, parent_scope):
    foreign_root = catalog.publish(
        replace(taxon("foreign-grand", "Foreign grandparent"), provider="other"), retrieved_at=NOW
    )
    parent = catalog.publish(
        replace(
            taxon("foreign-parent", "Foreign parent", parent_provider_id="foreign-grand"),
            provider="other",
        ),
        retrieved_at=NOW,
    )
    catalog.map_identity(
        parent,
        "fixture",
        "parent",
        source_url="https://example.test/parent",
        decided_by="Owner",
        reason="Explicit cross-provider parent identity",
    )
    facts = [
        taxon("grand", "Fixture grandparent"),
        taxon("parent", "Fixture parent", parent_provider_id="grand"),
    ]
    if parent_scope == "overlay":
        for fact in facts:
            catalog.publish(fact, retrieved_at=NOW)
    else:
        generation = stage(catalog, "Fixture ancestry", facts)
        for conflict in catalog.conflicts():
            catalog.resolve_conflict(
                conflict.conflict_id, decided_by="Owner", reason="Retain origin"
            )
        catalog.promote(generation)
    child = catalog.publish(
        taxon("child", "Fixture child", parent_provider_id="parent"), retrieved_at=NOW
    )
    assert [item.scientific_name for item in catalog.resolve(child).ancestry] == [
        "Fixture parent",
        "Fixture grandparent",
    ]
    assert catalog.resolve(parent).scientific_name == "Foreign parent"
    assert foreign_root not in {item.taxon_id for item in catalog.resolve(child).ancestry}


@pytest.mark.parametrize("old_clock", [None, NOW - timedelta(days=2)])
@pytest.mark.parametrize("action", ["cleanup", "rollback"])
def test_historical_generation_conflict_does_not_taint_newer_selected_view(
    catalog, old_clock, action
):
    a = catalog.begin_generation(
        replace(source("Historical reference"), snapshot_at=old_clock), imported_at=NOW
    )
    catalog.stage(a, [taxon("1", "Historical taxonomy")])
    catalog.validate_generation(a)
    catalog.promote(a)
    b = catalog.begin_generation(
        replace(source("Newer reference"), snapshot_at=NOW), imported_at=NOW
    )
    catalog.stage(b, [taxon("1", "Newer taxonomy")])
    catalog.validate_generation(b)
    for conflict in catalog.conflicts():
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain qualified newer reference"
        )
    catalog.promote(b)
    identifier = catalog.publish(
        taxon("1", "Historical live observation"),
        retrieved_at=NOW,
        source_effective_at=old_clock or NOW - timedelta(days=1),
    )
    pending = catalog.conflicts()
    assert pending and all(conflict.generation_id == a for conflict in pending)
    selected = catalog.resolve(identifier)
    assert selected.scientific_name == "Newer taxonomy"
    assert selected.selection_state == "selected"
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(a)
    if action == "cleanup":
        catalog.cleanup(a, retained_generations={b})
        assert catalog.conflicts() == pending
        assert catalog.resolve(identifier).selection_state == "selected"
        assert catalog.resolve(identifier).scientific_name == "Newer taxonomy"
    else:
        for conflict in pending:
            catalog.resolve_conflict(
                conflict.conflict_id,
                decided_by="Owner",
                reason="Explicit historical rollback decision",
            )
        catalog.promote(a)
        assert catalog.active_generation() == a
        assert catalog.resolve(identifier).selection_state == "selected"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("separate_batches", [False, True])
@pytest.mark.parametrize("synonym", [False, True])
def test_qualified_alias_records_coalesce_deterministically_and_remain_searchable(
    catalog, reverse, separate_batches, synonym
):
    canonical = taxon(
        "1",
        "Reference target",
        preferred_common_name="Current common",
        source_effective_at=NOW - timedelta(days=2),
    )
    identifier = catalog.publish(canonical, retrieved_at=NOW)
    catalog.map_identity(
        identifier,
        "fixture",
        "alias",
        source_url="https://example.test/alias",
        decided_by="Owner",
        reason="Qualified provider alias",
    )
    a = stage(catalog, "Rollback root", [taxon("root", "Unrelated reference")])
    catalog.promote(a)
    alias = taxon(
        "alias",
        "Historical synonym" if synonym else "Reference target",
        preferred_common_name="Former common" if synonym else "Current common",
        taxonomic_status="synonym" if synonym else canonical.taxonomic_status,
        accepted_provider_id="1" if synonym else None,
    )
    records = [canonical, alias]
    if reverse:
        records.reverse()
    b = catalog.begin_generation(
        replace(source("Qualified aliases"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
    )
    if separate_batches:
        for record in records:
            catalog.stage(b, [record])
    else:
        catalog.stage(b, records)
    catalog.stage(b, [taxon("child", "Reference child", parent_provider_id="alias")])
    catalog.validate_generation(b)
    assert catalog.conflicts() == ()
    catalog.promote(b)
    selected = catalog.resolve(identifier)
    assert selected.provider_id == "1"
    assert selected.scientific_name == "Reference target"
    assert {r.provider_id for r in selected.provider_references} == {"1", "alias"}
    child = catalog.search("Reference child")[0]
    assert [ancestor.taxon_id for ancestor in child.ancestry] == [identifier]
    if synonym:
        assert "Historical synonym" in selected.synonyms
        assert "Former common" in selected.common_names
        assert catalog.search("Historical synonym")[0].taxon_id == identifier
    catalog.promote(a)
    catalog.cleanup(b, retained_generations={a})
    assert catalog.resolve(identifier).taxon_id == identifier
    if synonym:
        assert catalog.search("Historical synonym")[0].taxon_id == identifier


def test_qualified_alias_fact_disagreement_requires_a_fresh_content_bound_decision(catalog):
    identifier = catalog.publish(
        taxon("1", "Chosen name"), retrieved_at=NOW, source_effective_at=NOW
    )
    for alias in ("2", "3"):
        catalog.map_identity(
            identifier,
            "fixture",
            alias,
            source_url="https://example.test/" + alias,
            decided_by="Owner",
            reason="Explicit qualified identity",
        )
    g = catalog.begin_generation(
        replace(source("Alias conflict"), snapshot_at=NOW + timedelta(days=1)), imported_at=NOW
    )
    catalog.stage(g, [taxon("2", "Conflicting second name"), taxon("1", "Chosen name")])
    first = [c for c in catalog.conflicts() if c.kind == "qualified_alias_facts"]
    assert len(first) == 1
    catalog.resolve_conflict(
        first[0].conflict_id, decided_by="Owner", reason="Retain deterministic canonical fact"
    )
    catalog.stage(g, [taxon("3", "Different third name")])
    pending = [c for c in catalog.conflicts() if c.kind == "qualified_alias_facts"]
    assert pending and pending[0].conflict_id != first[0].conflict_id
    assert pending[0].details != first[0].details
    catalog.validate_generation(g)
    with pytest.raises(TaxonomyConflictError):
        catalog.promote(g)
    for conflict in pending:
        catalog.resolve_conflict(
            conflict.conflict_id, decided_by="Owner", reason="Retain recorded canonical facts"
        )
    catalog.promote(g)
    assert catalog.resolve(identifier).scientific_name == "Chosen name"


def test_repeated_provider_id_still_rejected_after_alias_coalescing(catalog):
    identifier = catalog.publish(
        taxon("z", "Same name"), retrieved_at=NOW, source_effective_at=NOW - timedelta(days=20)
    )
    catalog.map_identity(
        identifier,
        "fixture",
        "a",
        source_url="https://example.test/a",
        decided_by="Owner",
        reason="Qualified alias",
    )
    g = catalog.begin_generation(source("Duplicate input"), imported_at=NOW)
    catalog.stage(g, [taxon("z", "Same name")])
    catalog.stage(g, [taxon("a", "Same name")])
    with pytest.raises(ValueError, match="duplicate"):
        catalog.stage(g, [taxon("z", "Same name")])
    catalog.validate_generation(g)
    catalog.promote(g)
    assert catalog.resolve(identifier).provider_id == "a"


def test_parent_alias_of_own_uuid_is_still_a_generation_cycle(catalog):
    identifier = catalog.publish(taxon(), retrieved_at=NOW)
    catalog.map_identity(
        identifier,
        "fixture",
        "alias",
        source_url="https://example.test/alias",
        decided_by="Owner",
        reason="Qualified alias",
    )
    g = catalog.begin_generation(source("Self parent through alias"), imported_at=NOW)
    catalog.stage(g, [taxon(parent_provider_id="alias")])
    with pytest.raises(ValueError, match="cycle"):
        catalog.validate_generation(g)


def test_equivalent_alias_metadata_does_not_reopen_unchanged_ordering_decision(catalog):
    identifier = catalog.publish(
        taxon("1", "Live selection"), retrieved_at=NOW, source_effective_at=NOW
    )
    catalog.map_identity(
        identifier,
        "fixture",
        "z",
        source_url="https://example.test/z",
        decided_by="Owner",
        reason="Qualified equivalent identity",
    )
    g = catalog.begin_generation(replace(source("Same clock"), snapshot_at=NOW), imported_at=NOW)
    catalog.stage(g, [taxon("1", "Snapshot comparison")])
    pending = catalog.conflicts()
    assert len(pending) == 1 and pending[0].kind == "equal_freshness"
    catalog.resolve_conflict(
        pending[0].conflict_id, decided_by="Owner", reason="Retain the reviewed comparison"
    )
    catalog.stage(g, [taxon("z", "Snapshot comparison")])
    assert catalog.conflicts() == ()
    catalog.validate_generation(g)
    catalog.promote(g)
    assert catalog.active_generation() == g


def test_resolve_returns_all_127_ancestors_allowed_by_generation_validation(catalog):
    records = [
        taxon(str(index), f"Ancestor {index}", parent_provider_id=str(index - 1) if index else None)
        for index in range(128)
    ]
    generation = stage(catalog, "Full supported ancestry", records)
    catalog.promote(generation)
    selected = catalog.search("Ancestor 127")[0]
    assert len(selected.ancestry) == 127
    assert [ancestor.scientific_name for ancestor in selected.ancestry] == [
        f"Ancestor {index}" for index in range(126, -1, -1)
    ]
