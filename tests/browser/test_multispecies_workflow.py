from __future__ import annotations

import re
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[2]
PHOTO = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def _client(tmp_path: Path) -> TestClient:
    database = tmp_path / "mixed-browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                runtime_secret=SecretStr("m55-browser-runtime-secret-32-bytes"),
                session_cookie_secure=False,
            )
        )
    )


def _setup(client: TestClient) -> None:
    setup = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": _csrf(setup.text),
            "household_name": "Mixed Household",
            "timezone": "UTC",
            "display_name": "Keeper",
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "password_confirmation": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _register(client: TestClient, name: str, animal_type: str, species: str) -> str:
    form = client.get("/animals/new")
    response = client.post(
        "/animals",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": f"m55-register-{name.lower().replace(' ', '-')}",
            "animal_type": animal_type,
            "name": name,
            "species": species,
            "sex": "",
            "morph": "",
            "genetics": "",
            "birth_hatch_date": "",
            "acquisition_date": "",
            "breeder_source": "",
            "notes": f"{name} keeper notes.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    profile_url = response.headers["location"]
    profile = client.get(profile_url)
    uploaded = client.post(
        f"{profile_url}/photo",
        data={
            "csrf_token": _csrf(profile.text),
            "idempotency_key": f"m55-photo-{name.lower().replace(' ', '-')}",
        },
        files={"photo": (f"{name}.png", PHOTO, "image/png")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 303
    return cast(str, profile_url)


def _create_enclosure(client: TestClient, name: str) -> str:
    form = client.get("/enclosures/new")
    response = client.post(
        "/enclosures",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": f"m55-enclosure-{name.lower().replace(' ', '-')}",
            "name": name,
            "enclosure_type": "terrarium",
            "notes": "Mixed household qualification fixture.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return cast(str, response.headers["location"])


def _assign(client: TestClient, animal_url: str, enclosure_url: str, key: str) -> None:
    profile = client.get(animal_url)
    response = client.post(
        f"{animal_url}/enclosure",
        data={
            "csrf_token": _csrf(profile.text),
            "idempotency_key": key,
            "enclosure_id": enclosure_url.rsplit("/", 1)[-1],
            "occurred_at": "2026-08-11T12:00",
            "notes": "Mixed collection placement.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_stock(client: TestClient) -> str:
    form = client.get("/inventory/new")
    created = client.post(
        "/inventory",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": "m55-shared-prey-stock",
            "name": "Shared feeder portions",
            "unit": "item",
            "reorder_threshold": "1",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    item_url = cast(str, created.headers["location"])
    item = client.get(item_url)
    received = client.post(
        f"{item_url}/receive",
        data={
            "csrf_token": _csrf(item.text),
            "idempotency_key": "m55-shared-prey-receive",
            "expected_stream_version": "1",
            "quantity": "5",
            "reference": "Mixed fixture stock",
        },
        follow_redirects=False,
    )
    assert received.status_code == 303
    return item_url


def _feed_from_stock(
    client: TestClient,
    animal_url: str,
    item_url: str,
    *,
    expected_stock_version: int,
    key: str,
    occurred_at: str,
) -> None:
    form = client.get(f"{animal_url}/feedings/new")
    response = client.post(
        f"{animal_url}/feedings",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": key,
            "occurred_at": occurred_at,
            "prey_type": "feeder portion",
            "prey_size": "small",
            "prey_weight_grams": "",
            "preparation_method": "other",
            "quantity": "1",
            "outcome": "accepted",
            "notes": "Shared inventory qualification.",
            "inventory_item_id": item_url.rsplit("/", 1)[-1],
            "inventory_expected_stream_version": str(expected_stock_version),
            "inventory_quantity": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_five_animal_mixed_collection_shows_type_photo_and_applicable_actions(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        profiles = {
            "Snake A": _register(client, "Snake A", "snake", "Python regius"),
            "Snake B": _register(client, "Snake B", "snake", "Boa imperator"),
            "Spider A": _register(client, "Spider A", "spider", "Grammostola pulchra"),
            "Spider B": _register(client, "Spider B", "spider", "Tliltocatl albopilosus"),
            "Spider C": _register(client, "Spider C", "spider", "Avicularia avicularia"),
        }

        collection = client.get("/animals")
        assert collection.status_code == 200
        for name in profiles:
            assert name in collection.text
            assert f'alt="Profile photo of {name}"' in collection.text
        assert collection.text.count(">Snake<") >= 2
        assert collection.text.count(">Spider<") >= 3

        snake = client.get(profiles["Snake A"])
        assert all(
            label in snake.text
            for label in (
                "Record feeding",
                "Record weight",
                "Record length",
                "Record shed",
                "Record bath",
            )
        )
        assert "Record molt" not in snake.text
        assert "Premolt observation" not in snake.text
        assert "Record misting" not in snake.text
        assert "Length check" in snake.text
        assert "Molt check" not in snake.text

        spider = client.get(profiles["Spider A"])
        assert all(
            label in spider.text
            for label in (
                "Record feeding",
                "Record weight",
                "Record molt",
                "Premolt observation",
                "Record misting",
            )
        )
        assert "Record length" not in spider.text
        assert "Record shed" not in spider.text
        assert "Record bath" not in spider.text
        assert "Molt check" in spider.text
        assert "Length check" not in spider.text
        assert "Premolt state" in spider.text
        assert "Not recorded" in spider.text

        direct_snake_form = client.get(f"{profiles['Spider A']}/lengths/new")
        assert direct_snake_form.status_code == 422
        assert "not available" in direct_snake_form.text
        malformed_animal_form = client.get("/animals/not-a-uuid/molts/new")
        assert malformed_animal_form.status_code == 404
        assert "Animal not found" in malformed_animal_form.text

        snake_habitat = _create_enclosure(client, "Snake Habitat")
        spider_tower = _create_enclosure(client, "Spider Tower")
        spider_nursery = _create_enclosure(client, "Spider Nursery")
        _assign(client, profiles["Snake A"], snake_habitat, "m55-assign-snake-a")
        _assign(client, profiles["Snake B"], snake_habitat, "m55-assign-snake-b")
        _assign(client, profiles["Spider A"], spider_tower, "m55-assign-spider-a-first")
        _assign(client, profiles["Spider B"], spider_nursery, "m55-assign-spider-b")
        _assign(client, profiles["Spider C"], spider_nursery, "m55-assign-spider-c")
        _assign(client, profiles["Spider A"], spider_nursery, "m55-assign-spider-a-second")

        old_occupancy = client.get(spider_tower)
        current_occupancy = client.get(spider_nursery)
        assert "Spider A" not in old_occupancy.text
        assert all(name in current_occupancy.text for name in ("Spider A", "Spider B", "Spider C"))
        assert "Spider Nursery" in client.get(profiles["Spider A"]).text

        occurred_at = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
        shared_stock = _create_stock(client)
        _feed_from_stock(
            client,
            profiles["Snake A"],
            shared_stock,
            expected_stock_version=2,
            key="m55-browser-snake-feeding",
            occurred_at=occurred_at,
        )
        _feed_from_stock(
            client,
            profiles["Spider B"],
            shared_stock,
            expected_stock_version=3,
            key="m55-browser-spider-feeding",
            occurred_at=occurred_at,
        )
        assert "3 item" in client.get(shared_stock).text

        spider_profile = client.get(profiles["Spider A"])
        molt = client.post(
            f"{profiles['Spider A']}/molts",
            data={
                "csrf_token": _csrf(spider_profile.text),
                "idempotency_key": "m55-browser-spider-molt",
                "occurred_at": occurred_at,
                "result": "complete",
                "notes": "Clean molt.",
            },
            follow_redirects=False,
        )
        assert molt.status_code == 303
        spider_profile = client.get(profiles["Spider A"])
        premolt = client.post(
            f"{profiles['Spider A']}/premolt-observations",
            data={
                "csrf_token": _csrf(spider_profile.text),
                "idempotency_key": "m55-browser-spider-premolt",
                "occurred_at": occurred_at,
                "observed": "true",
                "notes": "Darkened abdomen.",
            },
            follow_redirects=False,
        )
        assert premolt.status_code == 303
        spider_profile = client.get(profiles["Spider A"])
        assert "Premolt state" in spider_profile.text
        assert "Observed · Darkened abdomen." in spider_profile.text
        cleared_premolt = client.post(
            f"{profiles['Spider A']}/premolt-observations",
            data={
                "csrf_token": _csrf(spider_profile.text),
                "idempotency_key": "m55-browser-spider-premolt-cleared",
                "occurred_at": occurred_at,
                "observed": "false",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert cleared_premolt.status_code == 303
        spider_profile = client.get(profiles["Spider A"])
        assert "Premolt state" in spider_profile.text
        assert "Cleared" in spider_profile.text
        misting = client.post(
            f"{profiles['Spider A']}/mistings",
            data={
                "csrf_token": _csrf(spider_profile.text),
                "idempotency_key": "m55-browser-spider-misting",
                "occurred_at": occurred_at,
                "duration_seconds": "20",
                "notes": "Light wall mist.",
            },
            follow_redirects=False,
        )
        assert misting.status_code == 303

        timeline = client.get(f"{profiles['Spider A']}/timeline")
        assert "Molt recorded" in timeline.text
        assert "Complete · Clean molt." in timeline.text
        assert "Premolt observed" in timeline.text
        assert "Darkened abdomen." in timeline.text
        assert "Misting recorded" in timeline.text
        assert "20 seconds · Light wall mist." in timeline.text

        spider_profile = client.get(profiles["Spider A"])
        schedule = client.post(
            f"{profiles['Spider A']}/care-schedule/molt",
            data={
                "csrf_token": _csrf(spider_profile.text),
                "idempotency_key": "m55-browser-spider-molt-schedule",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "21",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert schedule.status_code == 303
        agenda = client.get("/reminders")
        assert "Spider A" in agenda.text
        assert "Molt" in agenda.text

        home = client.get("/home")
        logged_out = client.post(
            "/logout",
            data={"csrf_token": _csrf(home.text)},
            follow_redirects=False,
        )
        assert logged_out.status_code == 303
        protected = client.get(profiles["Spider A"], follow_redirects=False)
        assert protected.status_code == 303
        assert protected.headers["location"] == "/login"
