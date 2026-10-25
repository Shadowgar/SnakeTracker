from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.application.natural_history import NaturalHistoryVersion
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "reference/natural-history/boa-imperator-development.json"


def csrf(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


def seed(path):
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(path, require_local_storage=False)
    candidate = ProviderTaxon(
        provider="inaturalist",
        provider_id="539399",
        source_url="https://www.inaturalist.org/taxa/539399",
        supported_group="snake",
        accepted_scientific_name="Boa imperator",
        preferred_common_name="Central American Boa",
        kingdom="Animalia",
        phylum_division="Chordata",
        class_name="Reptilia",
        order_name="Squamata",
        family="Boidae",
        genus="Boa",
        rank="species",
    )
    identifier = LocalTaxonomyCatalog(engine).publish(candidate, retrieved_at=datetime.now(UTC))
    data = NaturalHistoryVersion.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    data["taxon_id"] = str(identifier)
    item = NaturalHistoryVersion.model_validate(data)
    repo = NaturalHistoryRepository(engine)
    key = repo.retain(item)
    repo.select(
        key,
        expected_revision=0,
        content_sha256=item.digest,
        actor="development reviewer",
        reason="Local Boa acceptance fixture; not production",
        development=True,
    )
    engine.dispose()
    settings = Settings(
        environment=Environment.TEST,
        database_path=path,
        runtime_secret=SecretStr("fictional-natural-history-preview-secret"),
        session_cookie_secure=False,
    )
    return build_application(settings), identifier


def setup_animal(client, identifier):
    response = client.post(
        "/setup",
        data={
            "csrf_token": csrf(client.get("/setup")),
            "household_name": "Natural History preview",
            "timezone": "UTC",
            "display_name": "Preview keeper",
            "email": "natural-history@example.test",
            "password": "Fictional natural history preview 2026!",
            "password_confirmation": "Fictional natural history preview 2026!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    form = client.get("/animals/new")
    response = client.post(
        "/animals",
        data={
            "csrf_token": csrf(form),
            "idempotency_key": "fictional-boa-registration",
            "animal_type": "snake",
            "name": "Cedar",
            "species": "Central American Boa",
            "taxon_id": str(identifier),
            "photo_preference": "none",
            "sex": "",
            "morph": "",
            "genetics": "",
            "birth_hatch_date": "",
            "acquisition_date": "",
            "breeder_source": "",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def snapshot(path):
    with sqlite3.connect(path) as c:
        tables = [
            row[0]
            for row in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        # Auth/security bookkeeping is expressly permitted. Every other persisted table
        # is compared, including catalog, guides, jobs, events, media and search.
        permitted = {"sessions", "security_audit"}
        return {
            name: sorted(map(repr, c.execute('SELECT * FROM "' + name + '"').fetchall()))
            for name in tables
            if name not in permitted
        }


def test_boa_offline_local_reference_and_private_access(tmp_path, monkeypatch):
    path = tmp_path / "boa.sqlite3"
    app, identifier = seed(path)
    with TestClient(app) as client:
        animal = setup_animal(client, identifier)

        # Block transports only after fixture setup; ordinary viewing must never use them.
        def offline(*args, **kwargs):
            raise AssertionError("Outbound download during ordinary read")

        monkeypatch.setattr("urllib.request.urlopen", offline)
        monkeypatch.setattr("snaketracker.infrastructure.taxonomy.inaturalist.urlopen", offline)
        monkeypatch.setattr(
            "snaketracker.infrastructure.taxonomy.reference_providers.urlopen", offline
        )
        monkeypatch.setattr(
            "snaketracker.infrastructure.taxonomy.inaturalist.INaturalistTaxonomyProvider.detail",
            offline,
        )
        before = snapshot(path)
        for url in (animal, animal + "/reference", "/directory/" + str(identifier)):
            page = client.get(url)
            assert page.status_code == 200, page.text
            if url != animal:
                assert "Wikipedia contributors" in page.text
                assert "1380867968" in page.text
                assert "No reviewed captive-care guide is available yet." in page.text
                assert "Where it lives" in page.text
                assert "not care recommendations" in page.text
            assert "<script>bad" not in page.text
        assert (
            "/static/species-references/boa-imperator.webp"
            in client.get(animal + "/reference").text
        )
        assert client.get("/static/species-references/boa-imperator.webp").status_code == 200
        assert snapshot(path) == before
        # Warm and cold optional content remain ordinary local reads.
        engine = create_sqlite_engine(path, require_local_storage=False)
        repo = NaturalHistoryRepository(engine)
        key = repo.decisions(identifier)[0]["association_id"]
        repo.withdraw(key, expected_revision=1, actor="reviewer", reason="Fixture withdrawal")
        before = snapshot(path)
        page = client.get(animal + "/reference")
        assert "Natural History is not available yet." in page.text
        assert snapshot(path) == before
        engine.dispose()
    with TestClient(app) as stranger:
        response = stranger.get(animal + "/reference", follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/login"


def test_qualified_legacy_biology_displays_once_without_rewriting_full_guide(tmp_path):
    from snaketracker.application.care_guides import GuideBundle
    from snaketracker.application.natural_history import GuideBiologyBinding, guide_digest
    from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
    from tests.integration.test_care_guides import _bundle

    path = tmp_path / "legacy.sqlite3"
    app, identifier = seed(path)
    engine = create_sqlite_engine(path, require_local_storage=False)
    original = _bundle().guides[0]
    claim = original.claims[0].model_copy(
        update={
            "fact_key": "natural_habitat",
            "value_text": "Fictional cloud forest",
            "value_number": None,
            "minimum": None,
            "maximum": None,
            "unit": None,
            "life_stage": "Adult",
            "context": "wild",
            "scope": "Boa imperator",
            "qualifier": None,
        }
    )
    guide = original.model_copy(update={"scientific_name": "Boa imperator", "claims": (claim,)})
    guides = SQLAlchemyCareGuideRepository(engine)
    guides.import_bundle(GuideBundle(format_version=1, guides=(guide,)))
    binding = GuideBiologyBinding(
        kind="habitat",
        life_stage="Adult",
        geography="synthetic range",
        sex="unspecified",
        qualifiers="",
        guide_version=1,
        guide_sha256=guide_digest(guide),
        claim_id=claim.claim_id,
        origin=guide.sources[0].url,
        qualification="Synthetic classification fixture, not real biological evidence",
    )
    repo = NaturalHistoryRepository(engine)
    current = repo.published(identifier, include_development=True)[0]
    adapted = current.model_copy(
        update={
            "revision": "synthetic-legacy-binding",
            "sections": (),
            "guide_bindings": (binding,),
            "modifications": "Synthetic guide-binding acceptance fixture; no production content.",
        }
    )
    key = repo.retain(adapted)
    repo.select(
        key,
        expected_revision=1,
        content_sha256=adapted.digest,
        actor="test reviewer",
        reason="Synthetic guide integration",
        development=True,
    )
    before = guides.version(identifier, 1)
    with TestClient(app) as client:
        animal = setup_animal(client, identifier)
        page = client.get(animal + "/reference")
        assert page.status_code == 200
        assert page.text.count("Fictional cloud forest") == 1
        full = client.get("/directory/" + str(identifier) + "/care-guide?version=1")
        assert full.status_code == 200 and "Fictional cloud forest" in full.text
        assert guides.version(identifier, 1) == before
        # A later immutable guide reuses the claim ID with different content. The bound
        # version remains readable, and must not suppress the newer unbound claim.
        newer = guide.model_copy(
            update={
                "version": 2,
                "claims": (claim.model_copy(update={"value_text": "Newer guide habitat"}),),
            }
        )
        guides.import_bundle(GuideBundle(format_version=1, guides=(newer,)))
        for url in (animal + "/reference", "/directory/" + str(identifier)):
            updated = client.get(url)
            assert updated.status_code == 200
            assert updated.text.count("Fictional cloud forest") == 1
            if url == animal + "/reference":
                assert "Newer guide habitat" in updated.text
        assert guides.version(identifier, 1) == before
    engine.dispose()
