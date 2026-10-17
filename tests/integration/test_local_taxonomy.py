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
    assert catalog.resolve(identifier).selection_state == "unknown_order"
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
    assert catalog.resolve(identifier).selection_state == "unknown_order"
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
    catalog.stage(generation, [taxon(**{relationship: "1"})])
    with pytest.raises(ValueError, match="cycle"):
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
