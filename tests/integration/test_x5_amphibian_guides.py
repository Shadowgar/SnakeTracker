"""AT-AMPHREF-01: reviewed frog guides remain exact, global and immutable."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command

from snaketracker.application.care_guides import glance_claims, profile_reference_claims
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.taxonomy.care_guides import (
    CareGuideImportError,
    SQLAlchemyCareGuideRepository,
)
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.operations.import_care_guides import load_bundle
from tests.integration.test_household_bootstrap import migrated_engine
from tests.integration.test_taxonomy_compatibility import config_for
from tests.integration.test_x4_compatibility import table_hashes

ROOT = Path(__file__).parents[2]
BUNDLE = ROOT / "reference/care-guides/reviewed-amphibians-v1.json"
NOW = datetime(2026, 11, 2, tzinfo=UTC)


def frog(name, *, provider_id=None, **changes):
    return ProviderTaxon(
        provider="fixture",
        provider_id=provider_id or name,
        source_url="https://example.test/qualified-frog",
        supported_group="amphibian",
        accepted_scientific_name=name,
        rank="species",
        kingdom="Animalia",
        class_name="Amphibia",
        order_name="Anura",
        **changes,
    )


def test_bundle_has_species_scoped_sources_and_useful_selectors():
    bundle = load_bundle(BUNDLE)
    assert {g.scientific_name for g in bundle.guides} == {
        "Pelodryas caerulea",
        "Ceratophrys cranwelli",
    }
    for guide in bundle.guides:
        assert guide.biological_group == "amphibian"
        assert glance_claims(guide)
        assert profile_reference_claims(guide)
        assert all(c.scope == guide.scientific_name and c.context for c in guide.claims)
        assert all(s.retrieved_at.date() == NOW.date() for s in guide.sources)


def test_import_is_reference_only_idempotent_and_rejects_changed_version(tmp_path):
    path = tmp_path / "guides.sqlite3"
    engine = migrated_engine(path)
    try:
        bundle = load_bundle(BUNDLE)
        catalog = LocalTaxonomyCatalog(engine)
        for guide in bundle.guides:
            catalog.publish(frog(guide.scientific_name), retrieved_at=NOW)
        before = table_hashes(path)
        repo = SQLAlchemyCareGuideRepository(engine)
        assert repo.import_bundle(bundle) == (2, 0)
        assert repo.import_bundle(bundle) == (0, 2)
        after = table_hashes(path)
        assert {k for k in before if before[k] != after[k]} == {
            "care_guide_versions",
            "care_guide_sources",
            "care_guide_claims",
            "care_guide_current",
        }
        guide = bundle.guides[0]
        changed = guide.model_copy(update={"reviewed_at": datetime(2026, 11, 3, tzinfo=UTC)})
        with pytest.raises(CareGuideImportError, match="changed"):
            repo.import_bundle(bundle.model_copy(update={"guides": (changed,)}))
        assert table_hashes(path) == after
        with pytest.raises(RuntimeError, match="downgrade blocked"):
            command.downgrade(config_for(path), "0025_natural_history")
        assert table_hashes(path) == after
    finally:
        engine.dispose()


@pytest.mark.parametrize("case", ["missing", "ambiguous", "genus", "wrong_class", "inactive"])
def test_import_requires_exact_qualified_species(tmp_path, case):
    path = tmp_path / "rejected.sqlite3"
    engine = migrated_engine(path)
    try:
        bundle = load_bundle(BUNDLE)
        catalog = LocalTaxonomyCatalog(engine)
        for guide in bundle.guides:
            candidate = frog(guide.scientific_name)
            if case == "missing":
                candidate = replace(candidate, accepted_scientific_name="Ceratophrys ornata")
            if case == "genus":
                candidate = replace(candidate, rank="genus")
            if case == "wrong_class":
                candidate = replace(candidate, class_name="Reptilia")
            if case == "inactive":
                candidate = replace(candidate, taxonomic_status="inactive")
            catalog.publish(candidate, retrieved_at=NOW)
            if case == "ambiguous":
                catalog.publish(
                    replace(candidate, provider_id="duplicate-" + candidate.provider_id),
                    retrieved_at=NOW,
                )
        before = table_hashes(path)
        with pytest.raises(CareGuideImportError, match="exactly one"):
            SQLAlchemyCareGuideRepository(engine).import_bundle(bundle)
        assert table_hashes(path) == before
    finally:
        engine.dispose()


def seed_reference_animals(client):
    """Fictional animals linked only to individually qualified species fixtures."""
    import re

    catalog = LocalTaxonomyCatalog(client.app.state.database_engine)
    bundle = load_bundle(BUNDLE)
    paths = {}
    for name, common in (
        ("Pelodryas caerulea", "White's Tree Frog"),
        ("Ceratophrys cranwelli", "Cranwell's Horned Frog"),
        ("Rana temporaria", "Common Frog"),
    ):
        candidate = frog(
            name,
            preferred_common_name=common,
            synonyms=("Litoria caerulea", "Ranoidea caerulea")
            if name == "Pelodryas caerulea"
            else (),
        )
        identifier = catalog.publish(candidate, retrieved_at=NOW)
        form = client.get("/animals/new")
        token = re.search(r'name="csrf_token" value="([^"]+)"', form.text).group(1)
        response = client.post(
            "/animals",
            data={
                "csrf_token": token,
                "idempotency_key": "x5-" + name,
                "animal_type": "amphibian",
                "name": {
                    "Pelodryas caerulea": "Moss",
                    "Ceratophrys cranwelli": "Pebble",
                    "Rana temporaria": "Fern",
                }[name],
                "species": name,
                "taxon_id": str(identifier),
                "photo_preference": "none",
                "notes": "Fictional Animal for isolated X5 design review.",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        paths[name] = response.headers["location"]
    SQLAlchemyCareGuideRepository(client.app.state.database_engine).import_bundle(bundle)
    return paths


def test_reference_view_is_offline_and_keeps_context_cautions_and_no_guide(tmp_path, monkeypatch):
    import socket

    from tests.browser.test_multispecies_workflow import _client, _setup

    with _client(tmp_path) as client:
        _setup(client)
        paths = seed_reference_animals(client)
        database = tmp_path / "mixed-browser.sqlite3"
        before = table_hashes(database)

        def no_network(*args, **kwargs):
            pytest.fail("Ordinary reference viewing attempted network I/O")

        monkeypatch.setattr(socket.socket, "connect", no_network)
        for name, url in paths.items():
            page = client.get(url + "/reference")
            assert page.status_code == 200
            assert "Species Overview / Natural History" in page.text
            assert "Reviewed Captive Care" in page.text
            if name == "Rana temporaria":
                assert "No reviewed captive-care guide is available yet." in page.text
            else:
                assert 'class="profile-reference-cautions"' in page.text
                assert "2026-11-02" in page.text
                assert "No reviewed tadpole or breeding guidance" in page.text
                if name == "Pelodryas caerulea":
                    assert "Captive · middle of vivarium" in page.text
                    assert "Sources differ" in page.text
                    assert "Corroborated" in page.text
                else:
                    assert "C. cranwelli and C. ornata" in page.text
        after = table_hashes(database)
        # Session last-use bookkeeping is independent of reference/household state.
        assert {k for k in before if before[k] != after[k]} <= {"sessions", "security_audit"}


def test_source_positions_keep_adult_feeding_disagreement_and_juvenile_agreement():
    from snaketracker.application.care_guides import grouped_claims

    guide = load_bundle(BUNDLE).guides[0]
    facts = {
        (claims[0].fact_key, claims[0].life_stage): (claims, state)
        for _, section in grouped_claims(guide)
        for _, claims, state in section
    }
    adult, state = facts[("feeding_interval", "Adult")]
    assert state == "Sources differ"
    assert {c.source_id for c in adult} == {"rvc-white-2024", "nsw-water"}
    assert any(c.value_number == 2 and c.unit == "days" for c in adult)
    assert any("2\u20133 times weekly" in (c.value_text or "") for c in adult)
    assert facts[("feeding_interval", "Juvenile")][1] == "Corroborated"


def test_uvb_positions_and_critical_heat_controls_are_not_hidden():
    from snaketracker.application.care_guides import grouped_claims

    guide = load_bundle(BUNDLE).guides[0]
    uvb = next(
        (claims, state)
        for _, section in grouped_claims(guide)
        for _, claims, state in section
        if claims[0].fact_key == "uvb"
    )
    assert uvb[1] == "Sources differ"
    assert {c.source_id for c in uvb[0]} == {"rvc-white-2024", "nsw-environment"}
    heat = next(c for c in guide.claims if c.fact_key == "heat_safety")
    assert "thermostat" in heat.caution.lower()
    assert "thermometer" in heat.caution.lower()


def test_natural_history_remains_available_without_guide_and_manual_animal_stays_valid(tmp_path):
    from uuid import UUID

    from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository
    from tests.browser.test_multispecies_workflow import _client, _register, _setup
    from tests.integration.test_natural_history import version

    with _client(tmp_path) as client:
        _setup(client)
        paths = seed_reference_animals(client)
        engine = client.app.state.database_engine
        with engine.connect() as c:
            identifier = UUID(
                c.exec_driver_sql(
                    "SELECT taxon_id FROM taxa WHERE accepted_scientific_name='Rana temporaria'"
                ).scalar_one()
            )
        item = version(
            identifier,
            origin="https://example.test/frog-history",
            revision="fixture-1",
            revision_url="https://example.test/frog-history?revision=fixture-1",
            source_title="Synthetic Natural History qualification fixture",
            attribution="Care Keeper test fixture",
            verified_name="Rana temporaria",
            identity_provider="fixture",
            identity_provider_id="Rana temporaria",
            identity_evidence="https://example.test/qualified-frog",
            sections=[{"title": "About this species", "text": "Synthetic local reference text."}],
        )
        repo = NaturalHistoryRepository(engine)
        key = repo.retain(item)
        repo.select(
            key,
            expected_revision=0,
            content_sha256=item.digest,
            actor="X5 test",
            reason="Isolated fictional fixture",
            development=True,
        )
        page = client.get(paths["Rana temporaria"] + "/reference")
        assert "Synthetic local reference text." in page.text
        assert "No reviewed captive-care guide is available yet." in page.text
        manual = _register(client, "Unlinked", "amphibian", "Pelodryas caerulea")
        page = client.get(manual + "/reference")
        assert "Your manual species record remains valid." in page.text
        assert "Choose a linked species to check for a reviewed captive-care guide." in page.text
        assert "profile-reference-cautions" not in page.text
