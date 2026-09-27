#!/usr/bin/env python3
"""Build a disposable fictional M6.6-B browser dataset under /tmp only."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.application.care_guides import GuideBundle
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository

ROOT = Path(__file__).parents[2]


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if match is None:
        raise RuntimeError("Isolated form has no CSRF token")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    arguments = parser.parse_args()
    target = arguments.data_dir.resolve()
    if target.parent != Path("/tmp") or not target.name.startswith("m66b-browser."):
        parser.error("Browser data must be a new /tmp/m66b-browser.* directory")
    if any(target.iterdir()):
        parser.error("Browser data directory must be empty")
    database = target / "snaketracker.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    engine = create_sqlite_engine(database, require_local_storage=False)
    taxon_ids = {}
    repository = SQLAlchemyTaxonRepository(engine)
    for index, guide in enumerate(bundle.guides, start=1):
        taxon = repository.upsert(
            ProviderTaxon(
                provider="fixture",
                provider_id=str(index),
                source_url=f"https://example.test/taxa/{index}",
                supported_group=guide.biological_group.value,
                accepted_scientific_name=guide.scientific_name,
                preferred_common_name={
                    "Python regius": "Ball python",
                    "Pogona vitticeps": "Bearded dragon",
                    "Avicularia avicularia": "Pink-toed tarantula",
                    "Pandinus imperator": "Emperor scorpion",
                    "Monstera deliciosa": "Swiss cheese plant",
                }[guide.scientific_name],
                rank="species",
                kingdom="Plantae" if guide.biological_group.value == "plant" else "Animalia",
                genus=guide.scientific_name.split()[0],
                species=guide.scientific_name,
            ),
            observed_at=datetime.now(UTC),
        )
        taxon_ids[guide.scientific_name] = str(taxon.taxon_id)
    no_guide = repository.upsert(
        ProviderTaxon(
            provider="fixture",
            provider_id="unreviewed-boa",
            source_url="https://example.test/taxa/unreviewed-boa",
            supported_group="snake",
            accepted_scientific_name="Boa constrictor",
            preferred_common_name="Boa constrictor",
            rank="species",
            kingdom="Animalia",
            genus="Boa",
            species="Boa constrictor",
        ),
        observed_at=datetime.now(UTC),
    )
    taxon_ids["Boa constrictor"] = str(no_guide.taxon_id)
    SQLAlchemyCareGuideRepository(engine).import_bundle(bundle)
    engine.dispose()
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            runtime_secret=SecretStr("m66b-fictional-browser-runtime-secret-32-bytes"),
            session_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        setup = client.get("/setup")
        created = client.post(
            "/setup",
            data={
                "csrf_token": csrf(setup.text),
                "household_name": "Fictional Guide Review",
                "timezone": "UTC",
                "display_name": "Demo Keeper",
                "email": "guide-review@example.test",
                "password": "fictional-guide-review-password",
                "password_confirmation": "fictional-guide-review-password",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        animal_form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": csrf(animal_form.text),
                "idempotency_key": "m66b-fictional-snake",
                "animal_type": "snake",
                "name": "Fictional Monty",
                "species": "Ball python",
                "taxon_id": taxon_ids["Python regius"],
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
        assert animal.status_code == 303, animal.text[:200]
        animal_urls = {"with_guide": animal.headers["location"]}
        for key, group, name, species, taxon_id in (
            (
                "disagreement",
                "lizard",
                "Fictional Draco",
                "Pogona vitticeps",
                taxon_ids["Pogona vitticeps"],
            ),
            (
                "linked_without_guide",
                "snake",
                "Fictional Boa",
                "Boa constrictor",
                taxon_ids["Boa constrictor"],
            ),
            ("unlinked", "snake", "Fictional Unlinked", "Python regius", ""),
        ):
            form = client.get("/animals/new")
            response = client.post(
                "/animals",
                data={
                    "csrf_token": csrf(form.text),
                    "idempotency_key": f"m66b-fictional-{key}",
                    "animal_type": group,
                    "name": name,
                    "species": species,
                    "taxon_id": taxon_id,
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
            assert response.status_code == 303, response.text[:200]
            animal_urls[key] = response.headers["location"]
        enclosure_form = client.get("/enclosures/new")
        enclosure = client.post(
            "/enclosures",
            data={
                "csrf_token": csrf(enclosure_form.text),
                "idempotency_key": "m66b-fictional-enclosure",
                "name": "Fictional terrarium",
                "enclosure_type_choice": "Glass terrarium",
                "custom_enclosure_type": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert enclosure.status_code == 303, enclosure.text[:200]
        enclosure_url = enclosure.headers["location"]
        plant_form = client.get(f"{enclosure_url}/plants/new")
        plant = client.post(
            f"{enclosure_url}/plants",
            data={
                "csrf_token": csrf(plant_form.text),
                "idempotency_key": "m66b-fictional-plant",
                "taxon_id": taxon_ids["Monstera deliciosa"],
                "manual_species": "Swiss cheese plant",
                "label": "Fictional plant",
                "quantity": "1",
                "date_added": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert plant.status_code == 303, plant.text[:200]
    manifest = {
        "taxon_ids": taxon_ids,
        "animal_url": animal.headers["location"],
        "animal_urls": animal_urls,
        "plant_url": plant.headers["location"],
        "database": str(database),
    }
    (target / "browser-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
