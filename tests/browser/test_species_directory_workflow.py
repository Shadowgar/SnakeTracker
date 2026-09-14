from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.application.species_directory import ProviderTaxon, TaxonRecord
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

ROOT = Path(__file__).parents[2]


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _client(tmp_path: Path) -> TestClient:
    database = tmp_path / "directory-browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                runtime_secret=SecretStr("directory-browser-runtime-secret-32-bytes"),
                session_cookie_secure=False,
            )
        )
    )


def _setup(client: TestClient) -> None:
    page = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": _csrf(page.text),
            "household_name": "Directory Home",
            "timezone": "UTC",
            "display_name": "Keeper",
            "email": "keeper@example.test",
            "password": "correct horse battery staple",
            "password_confirmation": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _cache(
    client: TestClient, provider_id: str, group: str, scientific: str, common: str
) -> TaxonRecord:
    application = cast(FastAPI, client.app)
    return SQLAlchemyTaxonRepository(application.state.database_engine).upsert(
        ProviderTaxon(
            provider="fixture",
            provider_id=provider_id,
            source_url=f"https://example.test/taxa/{provider_id}",
            supported_group=group,
            accepted_scientific_name=scientific,
            preferred_common_name=common,
            rank="species",
            kingdom="Plantae" if group == "plant" else "Animalia",
            family="Araceae" if group == "plant" else "Pythonidae",
            genus=scientific.split()[0],
            species=scientific,
        ),
        observed_at=datetime.now(UTC),
    )


def test_directory_animal_selection_manual_fallback_and_legacy_link(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        snake = _cache(client, "snake-1", "snake", "Python regius", "Ball Python")
        plant = _cache(client, "plant-1", "plant", "Epipremnum aureum", "Golden Pothos")

        form = client.get("/animals/new")
        assert 'role="combobox"' in form.text
        assert "Can't find it?" in form.text
        assert "/static/species-directory.js" in form.text
        suggestions = client.get("/api/directory/search?group=snake&q=ball+p")
        assert suggestions.status_code == 200
        assert suggestions.json()["records"][0]["scientific_name"] == "Python regius"
        timings = []
        for _ in range(20):
            started = perf_counter()
            cached = client.get("/api/directory/search?group=snake&q=ball+p")
            timings.append(perf_counter() - started)
            assert cached.status_code == 200
            assert cached.json()["state"] == "cached"
        assert sorted(timings)[18] < 0.25

        created = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(form.text),
                "idempotency_key": "directory-selected-animal",
                "animal_type": "snake",
                "name": "Monty",
                "species": "Ball Python",
                "taxon_id": str(snake.taxon_id),
                "sex": "",
                "morph": "Banana",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        profile = client.get(created.headers["location"])
        assert "Ball Python" in profile.text
        assert "Python regius" in profile.text
        assert "Banana" in profile.text
        assert "Change species link" in profile.text

        manual_form = client.get("/animals/new")
        manual = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(manual_form.text),
                "idempotency_key": "directory-manual-animal",
                "animal_type": "snake",
                "name": "Legacy",
                "species": "Uncatalogued snake",
                "taxon_id": "",
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
        assert manual.status_code == 303
        legacy_link = client.get(f"{manual.headers['location']}/species")
        assert "Nothing is linked until" in legacy_link.text
        linked = client.post(
            f"{manual.headers['location']}/species",
            data={
                "csrf_token": _csrf(legacy_link.text),
                "idempotency_key": "directory-legacy-link",
                "taxon_id": str(snake.taxon_id),
            },
            follow_redirects=False,
        )
        assert linked.status_code == 303
        legacy_profile = client.get(manual.headers["location"])
        assert "Ball Python" in legacy_profile.text

        directory = client.get("/directory?group=plant&q=pothos")
        assert "Golden Pothos" in directory.text
        detail = client.get(f"/directory/{plant.taxon_id}")
        assert "Epipremnum aureum" in detail.text
        assert "Araceae" in detail.text
        assert "Reference only" in detail.text
