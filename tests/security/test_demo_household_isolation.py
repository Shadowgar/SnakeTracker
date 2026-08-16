from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.engine import Engine

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from tests.integration.test_m6_owner_review_demo import seeder
from tests.integration.test_profile_photos import ONE_PIXEL_PNG

DEMO_EMAIL = seeder.DEMO_EMAIL
DEMO_PASSWORD = seeder.DEMO_PASSWORD
seed_demo = seeder.seed_demo
ROOT = Path(__file__).parents[2]


def migrated_engine(database: Path) -> Engine:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return create_sqlite_engine(database, require_local_storage=False)


def command_for() -> BootstrapCommand:
    return BootstrapCommand(
        household_name="Rocco's Reptiles",
        timezone="America/New_York",
        owner_email="owner@example.com",
        owner_display_name="Rocco",
        password="correct horse battery staple",
        idempotency_key="real-isolation-bootstrap",
        correlation_id=uuid4(),
    )


def csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def session_csrf(client: TestClient) -> str:
    token = client.cookies.get("snaketracker_csrf")
    assert token is not None
    return str(token)


def login(client: TestClient, email: str, password: str) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={"csrf_token": csrf(page.text), "email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_real_and_demo_households_cannot_read_or_mutate_each_other(tmp_path: Path) -> None:
    data_dir = tmp_path / "promoted-runtime"
    data_dir.mkdir()
    database = data_dir / "snaketracker.sqlite3"
    engine = migrated_engine(database)
    real = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    ).bootstrap(command_for())
    engine.dispose()
    demo = seed_demo(data_dir, as_of=None)
    with sqlite3.connect(database) as connection:
        demo_attachment = connection.execute(
            "SELECT photo_attachment_version_id FROM animal_current "
            "WHERE household_id=? AND animal_id=?",
            (demo.household_id, demo.animal_ids["Juniper"]),
        ).fetchone()[0]
    settings = Settings(
        environment=Environment.TEST,
        database_path=database,
        attachment_storage_path=data_dir / "attachments",
        runtime_secret=SecretStr("m6-owner-review-demo-runtime-secret"),
        session_cookie_secure=False,
    )

    real_app = build_application(settings)
    with TestClient(real_app) as real_client:
        login(real_client, "owner@example.com", "correct horse battery staple")
        form = real_client.get("/animals/new")
        created = real_client.post(
            "/animals",
            data={
                "csrf_token": csrf(form.text),
                "idempotency_key": "real-isolation-animal",
                "animal_type": "snake",
                "name": "Real Saffron",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "keeper-only-saffron-marker",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        real_animal_url = created.headers["location"]
        profile = real_client.get(real_animal_url)
        uploaded = real_client.post(
            f"{real_animal_url}/photo",
            data={"csrf_token": csrf(profile.text), "idempotency_key": "real-isolation-photo"},
            files={"photo": ("saffron.png", ONE_PIXEL_PNG, "image/png")},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303
        demo_animal_url = f"/animals/{demo.animal_ids['Juniper']}"
        assert real_client.get(demo_animal_url).status_code == 404
        assert real_client.get(f"/attachments/{demo_attachment}").status_code == 404
        assert "Juniper" not in real_client.get("/reports/collection").text
        assert "Juniper" not in real_client.get("/search?q=moonlit").text
        mutation = real_client.post(
            f"{demo_animal_url}/feedings",
            data={
                "csrf_token": session_csrf(real_client),
                "idempotency_key": "real-to-demo-denied",
                "occurred_at": "2026-08-16T12:00",
                "prey_type": "mouse",
                "prey_size": "small",
                "prey_weight_grams": "10",
                "preparation_method": "frozen_thawed",
                "quantity": "1",
                "outcome": "accepted",
                "notes": "must not write",
            },
        )
        assert mutation.status_code == 404

    with sqlite3.connect(database) as connection:
        real_animal_id = real_animal_url.rsplit("/", 1)[-1]
        real_attachment = connection.execute(
            "SELECT photo_attachment_version_id FROM animal_current "
            "WHERE household_id=? AND animal_id=?",
            (str(real.household_id), real_animal_id),
        ).fetchone()[0]
        real_stream_version = connection.execute(
            "SELECT current_version FROM event_streams WHERE household_id=? "
            "AND stream_type='animal' AND stream_id=?",
            (str(real.household_id), real_animal_id),
        ).fetchone()[0]

    demo_app = build_application(settings)
    with TestClient(demo_app) as demo_client:
        login(demo_client, DEMO_EMAIL, DEMO_PASSWORD)
        assert demo_client.get(real_animal_url).status_code == 404
        assert demo_client.get(f"/attachments/{demo_attachment}").status_code == 200
        assert demo_client.get(f"/attachments/{real_attachment}").status_code == 404
        assert "Real Saffron" not in demo_client.get("/reports/collection").text
        assert "Real Saffron" not in demo_client.get("/search?q=saffron").text

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT current_version FROM event_streams WHERE household_id=? "
            "AND stream_type='animal' AND stream_id=?",
            (str(real.household_id), real_animal_id),
        ).fetchone() == (real_stream_version,)
