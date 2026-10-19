from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from snaketracker.application.natural_history import NaturalHistoryVersion
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository
from tests.integration import test_local_taxonomy as taxonomy
from tests.integration.test_local_taxonomy import stage, taxon

catalog = taxonomy.catalog

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def version(identifier, **changes):
    return NaturalHistoryVersion.model_validate(
        {
            "taxon_id": str(identifier),
            "origin": "https://en.wikipedia.org/wiki/Boa_imperator",
            "revision": "1380867968",
            "revision_url": "https://en.wikipedia.org/w/index.php?title=Boa_imperator&oldid=1380867968",
            "source_title": "Boa imperator",
            "attribution": "Wikipedia contributors",
            "license": "CC BY-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "modifications": "Shortened and paraphrased; development example.",
            "retrieved_at": NOW.isoformat(),
            "verified_name": "Boa imperator",
            "identity_provider": "inaturalist",
            "identity_provider_id": "539399",
            "identity_evidence": "https://api.inaturalist.org/v1/taxa/539399",
            "rights_scope": "development",
            "rights_evidence": "Development fixture only; production qualification pending.",
            "sections": [
                {
                    "title": "About this species",
                    "text": "A nonvenomous boa native to Central America.",
                }
            ],
        }
        | changes
    )


def boa(catalog):
    return catalog.publish(
        replace(taxon("539399", "Boa imperator", "snake"), provider="inaturalist"), retrieved_at=NOW
    )


def test_retention_publication_withdrawal_and_exact_content(catalog):
    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(identifier)
    key = repo.retain(item)
    assert repo.retain(item) == key
    assert repo.published(identifier, include_development=True) == ()
    with pytest.raises(ValueError, match="rights"):
        repo.select(
            key,
            expected_revision=0,
            content_sha256=item.digest,
            actor="reviewer",
            reason="reviewed",
        )
    with pytest.raises(ValueError, match="content"):
        repo.select(
            key,
            expected_revision=0,
            content_sha256="0" * 64,
            actor="reviewer",
            reason="reviewed",
            development=True,
        )
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="reviewer",
        reason="development review",
        development=True,
    )
    assert repo.published(identifier) == ()
    assert repo.published(identifier, include_development=True) == (item,)
    second = version(
        identifier,
        revision="second",
        sections=[{"title": "About this species", "text": "A second retained description."}],
    )
    key2 = repo.retain(second)
    repo.select(
        key2,
        expected_revision=1,
        content_sha256=second.digest,
        actor="reviewer",
        reason="new version",
        development=True,
    )
    assert repo.versions(identifier) == (item, second)
    repo.withdraw(key2[0], expected_revision=2, actor="reviewer", reason="source withdrawn")
    assert repo.published(identifier, include_development=True) == ()
    assert len(repo.decisions(identifier)) == 3
    assert repo.versions(identifier) == (item, second)
    with catalog.engine.begin() as c, pytest.raises(IntegrityError, match="immutable"):
        c.execute(text("UPDATE natural_history_versions SET payload=:p"), {"p": "{}"})


def test_selection_race_and_conflicting_revision_are_explicit(catalog):
    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(identifier)
    key = repo.retain(item)
    with pytest.raises(ValueError, match="revision"):
        repo.retain(
            version(
                identifier,
                sections=[{"title": "About this species", "text": "Changed source revision text."}],
            )
        )

    def select(_):
        try:
            repo.select(
                key,
                expected_revision=0,
                content_sha256=item.digest,
                actor="reviewer",
                reason="reviewed",
                development=True,
            )
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(select, range(2))) == 1
    assert len(repo.decisions(identifier)) == 1


def test_content_survives_taxonomy_rollback_cleanup_and_names(catalog):
    a = stage(catalog, "A", [taxon("root", "Animalia")])
    catalog.promote(a)
    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(identifier)
    b = stage(catalog, "B", [taxon("root", "Animalia")])
    catalog.promote(b)
    key = repo.retain(item, generation_context=str(b))
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="reviewer",
        reason="reviewed",
        development=True,
    )
    catalog.promote(a)
    catalog.cleanup(b, retained_generations={a})
    assert repo.published(identifier, include_development=True) == (item,)
    assert catalog.resolve(identifier).scientific_name == "Boa imperator"
    assert not catalog.search("nonvenomous")


def test_identity_and_unsafe_source_validation(catalog):
    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    with pytest.raises(ValueError, match="identity"):
        repo.retain(version(identifier, identity_provider_id="wrong"))
    with pytest.raises(ValueError, match="identity"):
        repo.retain(version(identifier, verified_name="Boa constrictor"))
    for changes in [
        {"origin": "javascript:alert(1)"},
        {"sections": [{"title": "About this species", "text": "<script>bad</script>"}]},
        {"retrieved_at": "2026-10-18"},
        {"claims": [{"kind": "temperature", "value": "30"}]},
    ]:
        with pytest.raises(ValueError):
            version(identifier, **changes)


def test_production_qualification_and_audit_guards(catalog):
    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(
        identifier,
        rights_scope="production",
        rights_evidence="Synthetic rights qualification exercised only in isolated test.",
    )
    key = repo.retain(item)
    with pytest.raises(ValueError, match="actor"):
        repo.select(
            key, expected_revision=0, content_sha256=item.digest, actor="", reason="reviewed"
        )
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="rights reviewer",
        reason="Qualified exact source and content for synthetic test",
    )
    assert repo.published(identifier) == (item,)
    with catalog.engine.begin() as c, pytest.raises(IntegrityError, match="immutable"):
        c.exec_driver_sql("DELETE FROM natural_history_sources")
    with catalog.engine.begin() as c, pytest.raises(IntegrityError, match="immutable"):
        c.exec_driver_sql("DELETE FROM natural_history_decisions")


def test_startup_rejects_corrupt_publication_before_mutation(catalog):
    from snaketracker.bootstrap.compatibility import inspect_natural_history

    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(identifier)
    key = repo.retain(item)
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="reviewer",
        reason="fixture",
        development=True,
    )
    with catalog.engine.connect() as c:
        assert inspect_natural_history(c).normal_readiness
    with catalog.engine.begin() as c:
        c.exec_driver_sql("DROP TRIGGER natural_history_versions_no_update")
        c.exec_driver_sql("UPDATE natural_history_versions SET content_sha256='wrong'")
    with catalog.engine.connect() as c:
        assert not inspect_natural_history(c).normal_readiness
    with pytest.raises(ValueError, match="integrity"):
        repo.published(identifier, include_development=True)


def test_missing_selection_is_not_a_withdrawal(catalog):
    from snaketracker.bootstrap.compatibility import inspect_natural_history

    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    item = version(identifier)
    key = repo.retain(item)
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="reviewer",
        reason="fixture",
        development=True,
    )
    with catalog.engine.begin() as c:
        c.exec_driver_sql("DELETE FROM natural_history_selection")
    with catalog.engine.connect() as c:
        assert not inspect_natural_history(c).normal_readiness


def test_legacy_binding_preserves_life_stage_and_absent_qualifier(catalog):
    from snaketracker.application.care_guides import GuideBundle
    from snaketracker.application.natural_history import GuideBiologyBinding, guide_digest
    from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
    from tests.integration.test_care_guides import _bundle

    identifier = boa(catalog)
    repo = NaturalHistoryRepository(catalog.engine)
    original = _bundle().guides[0]
    claim = original.claims[0].model_copy(
        update={
            "fact_key": "natural_habitat",
            "value_text": "Forest",
            "value_number": None,
            "minimum": None,
            "maximum": None,
            "unit": None,
            "life_stage": "Juvenile",
            "context": "wild",
            "scope": "Boa imperator",
            "qualifier": None,
        }
    )
    guide = original.model_copy(update={"scientific_name": "Boa imperator", "claims": (claim,)})
    SQLAlchemyCareGuideRepository(catalog.engine).import_bundle(
        GuideBundle(format_version=1, guides=(guide,))
    )
    binding = GuideBiologyBinding(
        kind="habitat",
        life_stage="Juvenile",
        geography="species range",
        sex="unspecified",
        qualifiers="",
        guide_version=guide.version,
        guide_sha256=guide_digest(guide),
        claim_id=claim.claim_id,
        origin=guide.sources[0].url,
        qualification="Explicit qualified wild guide biology fixture",
    )
    valid = version(identifier, guide_bindings=[binding.model_dump()])
    assert repo.retain(valid)
    invalid = version(
        identifier,
        revision="other",
        guide_bindings=[binding.model_copy(update={"life_stage": "Adult"}).model_dump()],
    )
    with pytest.raises(ValueError, match="life stage"):
        repo.retain(invalid)
    for changes, message in [
        ({"guide_version": 999}, "exact retained"),
        ({"claim_id": "missing"}, "wild species"),
        ({"origin": "https://example.test/not-original"}, "original origin"),
        ({"qualifiers": "invented qualifier"}, "original origin"),
    ]:
        invalid = version(
            identifier,
            revision="rejected",
            guide_bindings=[binding.model_copy(update=changes).model_dump()],
        )
        with pytest.raises(ValueError, match=message):
            repo.retain(invalid)
    assert repo.versions(identifier) == (valid,)


def test_empty_or_repeated_description_sections_are_rejected(catalog):
    identifier = boa(catalog)
    with pytest.raises(ValueError, match="At least one"):
        version(identifier, sections=[])
    with pytest.raises(ValueError, match="unique"):
        version(
            identifier,
            sections=[
                {"title": "In the wild", "text": "First qualified section."},
                {"title": "In the wild", "text": "Repeated section title."},
            ],
        )
