#!/usr/bin/env python3
"""Serve a disposable X5 review fixture; no production paths or network during views."""

from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime
from pathlib import Path
from uuid import UUID

import uvicorn
from alembic import command
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.application.species_directory import ReferenceImageCandidate
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.taxonomy.reference_images import LocalReferenceImageCache
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository
from tests.browser.test_multispecies_workflow import _csrf, _setup
from tests.integration.test_taxonomy_compatibility import config_for
from tests.integration.test_x5_amphibian_guides import seed_reference_animals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--media-dir", type=Path)
    parser.add_argument("--port", type=int, default=8105)
    args = parser.parse_args()
    target = args.data_dir.resolve()
    if target.parent != Path("/tmp") or not target.name.startswith("carekeeper-x5-browser-"):
        parser.error("Use a new /tmp/carekeeper-x5-browser-* directory")
    target.mkdir(exist_ok=False)
    database = target / "review.sqlite3"
    command.upgrade(config_for(database), "head")
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            runtime_secret=SecretStr("x5-fictional-browser-runtime-secret-32-bytes"),
            attachment_storage_path=target / "attachments",
            reference_image_storage_path=target / "reference-images",
            backup_storage_path=target / "backups",
            session_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        _setup(client)
        paths = seed_reference_animals(client)
        if args.media_dir:
            root = Path(__file__).parents[2]
            manifest = (
                root
                / "docs/evidence/m6.6-species-aware-husbandry"
                / "x5-amphibian-reference/browser-media.json"
            )
            repository = SQLAlchemyTaxonRepository(app.state.database_engine)
            for item in json.loads(manifest.read_text()):
                species = item.pop("scientific_name")
                content = (args.media_dir / item.pop("local_file")).read_bytes()
                item["retrieved_at"] = datetime.fromisoformat(item["retrieved_at"])
                with app.state.database_engine.connect() as c:
                    identifier = UUID(
                        c.exec_driver_sql(
                            "SELECT taxon_id FROM taxa WHERE accepted_scientific_name=?", (species,)
                        ).scalar_one()
                    )
                candidate = ReferenceImageCandidate(**item)
                image_cache = LocalReferenceImageCache(
                    target / "reference-images",
                    fetch=lambda *_args, content=content: ("image/jpeg", content),
                )
                cached = image_cache.cache(identifier, candidate.download_url)
                repository.store_image_candidate(identifier, candidate)
                repository.mark_image_cached(identifier, cached)
                page = client.get(paths[species])
                response = client.post(
                    paths[species] + "/reference-photo",
                    data={
                        "csrf_token": _csrf(page.text),
                        "photo_preference": "species_reference",
                        "idempotency_key": "x5-media-" + species,
                    },
                    follow_redirects=False,
                )
                assert response.status_code == 303, response.text

    (target / "manifest.json").write_text(
        json.dumps(
            {
                "paths": paths,
                "database": str(database),
                "fictional": True,
                "origin": f"http://127.0.0.1:{args.port}",
            },
            indent=2,
        )
    )

    def forbidden_connect(*_args, **_kwargs):
        raise AssertionError("Network egress forbidden during X5 reference viewing")

    socket.socket.connect = forbidden_connect
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
