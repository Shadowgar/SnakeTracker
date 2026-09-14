from __future__ import annotations

import hashlib
import re
from base64 import b64decode
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import cast

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import text

from snaketracker.application.species_directory import ProviderTaxon, TaxonRecord
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

ROOT = Path(__file__).parents[2]
ONE_PIXEL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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
    client: TestClient,
    provider_id: str,
    group: str,
    scientific: str,
    common: str,
    *,
    image_license: str | None = None,
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
            image_source_url=(
                "https://static.inaturalist.org/photos/1/medium.jpg" if image_license else None
            ),
            image_creator="Jane Doe" if image_license else None,
            image_attribution="Jane Doe, CC BY" if image_license else None,
            image_license_code=image_license,
            image_license_url=(
                "https://creativecommons.org/licenses/by/4.0/" if image_license else None
            ),
        ),
        observed_at=datetime.now(UTC),
    )


def test_directory_animal_selection_manual_fallback_and_legacy_link(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        snake = _cache(
            client,
            "snake-1",
            "snake",
            "Python regius",
            "Ball Python",
            image_license="cc-by",
        )
        unlicensed = _cache(
            client, "snake-unlicensed", "snake", "Python bivittatus", "Burmese Python"
        )
        plant = _cache(client, "plant-1", "plant", "Epipremnum aureum", "Golden Pothos")

        image_output = BytesIO()
        Image.new("RGB", (80, 60), "brown").save(image_output, format="WEBP")
        image_content = image_output.getvalue()
        reference_root = tmp_path / "reference-images"
        reference_root.mkdir()
        reference_filename = f"{snake.taxon_id}.webp"
        (reference_root / reference_filename).write_bytes(image_content)
        application = cast(FastAPI, client.app)
        with application.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE taxon_images SET local_filename=:filename,"
                    "local_media_type='image/webp',local_byte_size=:byte_size,"
                    "local_sha256=:sha256,cached_at=:cached_at WHERE taxon_id=:taxon_id"
                ),
                {
                    "filename": reference_filename,
                    "byte_size": len(image_content),
                    "sha256": hashlib.sha256(image_content).hexdigest(),
                    "cached_at": datetime.now(UTC).isoformat(),
                    "taxon_id": str(snake.taxon_id),
                },
            )

        form = client.get("/animals/new")
        assert 'role="combobox"' in form.text
        assert "Can't find it?" in form.text
        assert "/static/species-directory.js" in form.text
        assert "Morph / variant" in form.text
        assert "Genetics / lineage" in form.text
        assert "Nothing is inferred from species" in form.text
        assert "Care Keeper never derives this from species" in form.text
        assert "More identity details" in form.text
        suggestions = client.get("/api/directory/search?group=snake&q=ball+p")
        assert suggestions.status_code == 200
        assert suggestions.json()["records"][0]["scientific_name"] == "Python regius"
        assert suggestions.json()["records"][0]["reference_image_available"] is True
        unlicensed_result = client.get("/api/directory/search?group=snake&q=burmese")
        assert unlicensed_result.status_code == 200
        assert unlicensed_result.json()["records"][0]["reference_image_available"] is False
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
                "photo_preference": "species_reference",
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
        assert "Species reference image" in profile.text
        assert "not your individual animal" not in profile.text
        assert "Add my animal's photo" in profile.text
        assert "CC BY" in profile.text
        reference = client.get(f"/directory/reference-images/{snake.taxon_id}")
        assert reference.status_code == 200
        assert reference.headers["content-type"] == "image/webp"
        assert reference.content == image_content
        assert "img-src &#39;self&#39;" not in profile.text
        assert profile.headers["content-security-policy"].split("; ")[3] == "img-src 'self'"
        assert "static.inaturalist.org" not in profile.text
        identity_suggestions = client.get(
            f"/api/directory/{snake.taxon_id}/identity-suggestions"
        ).json()
        assert identity_suggestions == {"morphs": ["Banana"], "genetics": []}

        photo_form = client.get(f"{created.headers['location']}/photo")
        invalid_preference = client.post(
            f"{created.headers['location']}/reference-photo",
            data={
                "csrf_token": _csrf(photo_form.text),
                "idempotency_key": "invalid-directory-reference-photo",
                "photo_preference": "invalid",
            },
        )
        assert invalid_preference.status_code == 422
        assert "valid reference-image preference" in invalid_preference.text

        photo_form = client.get(f"{created.headers['location']}/photo")
        disabled = client.post(
            f"{created.headers['location']}/reference-photo",
            data={
                "csrf_token": _csrf(photo_form.text),
                "idempotency_key": "disable-directory-reference-photo",
                "photo_preference": "none",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        disabled_profile = client.get(created.headers["location"])
        assert "Species reference image for Ball Python" not in disabled_profile.text
        assert "Add photo" in disabled_profile.text

        photo_form = client.get(f"{created.headers['location']}/photo")
        enabled = client.post(
            f"{created.headers['location']}/reference-photo",
            data={
                "csrf_token": _csrf(photo_form.text),
                "idempotency_key": "enable-directory-reference-photo",
                "photo_preference": "species_reference",
            },
            follow_redirects=False,
        )
        assert enabled.status_code == 303
        assert "Add my animal's photo" in client.get(created.headers["location"]).text

        photo_form = client.get(f"{created.headers['location']}/photo")
        assert "Add my animal's photo" in photo_form.text
        uploaded = client.post(
            f"{created.headers['location']}/photo",
            data={
                "csrf_token": _csrf(photo_form.text),
                "idempotency_key": "directory-personal-photo",
            },
            files={"photo": ("monty.png", ONE_PIXEL_PNG, "image/png")},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303
        personal_profile = client.get(created.headers["location"])
        assert "Profile photo of Monty" in personal_profile.text
        assert "Change photo" in personal_profile.text
        assert "Species reference image ·" not in personal_profile.text
        with application.state.database_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT local_filename FROM taxon_images WHERE taxon_id=:taxon_id"),
                    {"taxon_id": str(snake.taxon_id)},
                ).scalar_one()
                == reference_filename
            )

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
        assert manual.status_code == 303
        manual_profile = client.get(manual.headers["location"])
        assert "Add photo" in manual_profile.text

        declined_form = client.get("/animals/new")
        declined = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(declined_form.text),
                "idempotency_key": "directory-declined-reference-animal",
                "animal_type": "snake",
                "name": "No Reference",
                "species": "Ball Python",
                "taxon_id": str(snake.taxon_id),
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
        assert declined.status_code == 303
        declined_profile = client.get(declined.headers["location"])
        assert "Species reference image for Ball Python" not in declined_profile.text
        assert "Add photo" in declined_profile.text

        unavailable_form = client.get("/animals/new")
        unavailable = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(unavailable_form.text),
                "idempotency_key": "directory-unlicensed-reference-animal",
                "animal_type": "snake",
                "name": "Unlicensed",
                "species": "Burmese Python",
                "taxon_id": str(unlicensed.taxon_id),
                "photo_preference": "species_reference",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
        )
        assert unavailable.status_code == 422
        assert "licensed species reference image is not available" in unavailable.text
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
        assert "Reference directory" in detail.text
        assert "Add keeper-owned plants from an Enclosure" in detail.text
