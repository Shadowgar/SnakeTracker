#!/usr/bin/env python3
"""Prepare the correction review dataset in a new, empty /tmp fixture directory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository
from snaketracker.operations.import_care_guides import load_bundle

ROOT = Path(__file__).parents[2]


def csrf(response: str) -> str:
    import re

    match = re.search(r'name="csrf_token" value="([^"]+)"', response)
    if match is None:
        raise RuntimeError("Fictional fixture form has no CSRF token")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    arguments = parser.parse_args()
    target = arguments.data_dir.resolve()
    if target.parent != Path("/tmp") or not target.name.startswith("m66b-browser."):
        parser.error("Use a new, empty /tmp/m66b-browser.* directory")
    target.mkdir(exist_ok=True)
    if any(target.iterdir()):
        parser.error("Fixture directory must be empty; existing data cannot be replaced")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/qualification/m66b_prepare_browser.py"),
            "--data-dir",
            str(target),
        ],
        cwd=ROOT,
        check=True,
    )
    manifest_path = target / "browser-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    database = target / "snaketracker.sqlite3"
    if Path(manifest["database"]).resolve() != database:
        raise RuntimeError("Base fixture manifest points outside its disposable database")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        imported = SQLAlchemyCareGuideRepository(engine).import_bundle(
            load_bundle(ROOT / "reference/care-guides/reviewed-boa-constrictor-v1.json")
        )
        assert imported == (1, 0)
        taxon = SQLAlchemyTaxonRepository(engine).upsert(
            ProviderTaxon(
                provider="fixture",
                provider_id="morelia-no-guide",
                source_url="https://example.test/morelia",
                supported_group="snake",
                accepted_scientific_name="Morelia spilota",
                preferred_common_name="Carpet python",
                rank="species",
                kingdom="Animalia",
                genus="Morelia",
                species="Morelia spilota",
            ),
            observed_at=datetime.now(UTC),
        )
    finally:
        engine.dispose()
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            attachment_storage_path=target / "attachments",
            backup_storage_path=target / "backups",
            runtime_secret=SecretStr("m66b-fictional-browser-runtime-secret-32-bytes"),
            session_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        login = client.get("/login")
        authenticated = client.post(
            "/login",
            data={
                "csrf_token": csrf(login.text),
                "email": "guide-review@example.test",
                "password": "fictional-guide-review-password",
            },
            follow_redirects=False,
        )
        assert authenticated.status_code == 303
        form = client.get("/animals/new")
        response = client.post(
            "/animals",
            data={
                "csrf_token": csrf(form.text),
                "idempotency_key": "no-guide-morelia-browser",
                "animal_type": "snake",
                "name": "Fictional carpet python",
                "species": "Carpet python",
                "taxon_id": str(taxon.taxon_id),
                "photo_preference": "none",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text[:200]
        boa_route = manifest["animal_urls"]["linked_without_guide"]
        assert "Reviewed reference guidance" in client.get(boa_route).text
        assert (
            "No reviewed species guidance available yet."
            in client.get(response.headers["location"]).text
        )
    manifest["animal_urls"]["boa_guide"] = boa_route
    manifest["animal_urls"]["linked_without_guide"] = response.headers["location"]
    manifest["taxon_ids"]["Morelia spilota"] = str(taxon.taxon_id)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Correction fixture prepared: {manifest_path}")


if __name__ == "__main__":
    main()
