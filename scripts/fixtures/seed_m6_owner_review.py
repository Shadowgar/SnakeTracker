#!/usr/bin/env python3
"""Create the disposable, fictional M6 owner-review household."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pydantic import SecretStr

from snaketracker.application.household_bootstrap import DEMO_EMAIL, DEMO_HOUSEHOLD_ID
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.product_experience.projections import product_projection_registry
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.operations.demo_household import provision_demo_household

ROOT = Path(__file__).parents[2]
DEMO_PASSWORD = "m6-demo-local-only-password"
DEMO_SCENARIO_VERSION = "four-group-owner-review.v1"
DEMO_RUNTIME_SECRET = "m6-owner-review-demo-runtime-secret"
PHOTO_COLORS = {
    "juniper": (72, 112, 67),
    "atlas": (155, 103, 62),
    "ember": (157, 70, 45),
    "pip": (61, 114, 126),
    "nova": (89, 72, 126),
    "cedar": (135, 83, 45),
    "pearl": (126, 111, 133),
    "sol": (198, 143, 55),
    "bramble": (83, 112, 69),
    "dune": (177, 128, 79),
    "onyx": (44, 48, 55),
    "cobalt": (47, 79, 126),
    "saffron": (184, 113, 42),
}
DEMO_ANIMAL_NAMES = frozenset(
    {
        "Juniper",
        "Atlas",
        "Ember",
        "Pip",
        "Nova",
        "Cedar",
        "Pearl",
        "Sol",
        "Bramble",
        "Dune",
        "Onyx",
        "Cobalt",
        "Saffron",
    }
)


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    scenario_version: str
    database: str
    as_of: str
    household_id: str
    animal_count: int
    enclosure_count: int
    snake_count: int
    spider_count: int
    lizard_count: int
    scorpion_count: int
    profile_photo_count: int
    event_count: int
    prediction_ready: tuple[str, ...]
    insufficient_history_animals: tuple[str, ...]
    animal_ids: dict[str, str]


def _profile_photo(key: str, name: str) -> bytes:
    """Return a deterministic, visibly distinct fictional profile card."""
    image = Image.new("RGB", (640, 480), PHOTO_COLORS[key])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 80, 560, 400), radius=64, fill=(19, 32, 27), width=8)
    draw.ellipse((250, 135, 390, 275), fill=(181, 234, 77))
    draw.text((270, 300), name, fill=(245, 248, 240), anchor="ma")
    draw.text((320, 360), "FICTIONAL DEMO", fill=(181, 234, 77), anchor="mm")
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _form_time(value: date) -> str:
    return datetime.combine(value, time(12, 0), tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")


def _dates_from_intervals(last: date, intervals: tuple[int, ...]) -> tuple[date, ...]:
    values = [last - timedelta(days=sum(intervals))]
    for interval in intervals:
        values.append(values[-1] + timedelta(days=interval))
    return tuple(values)


def _csrf(client: TestClient) -> str:
    token = client.cookies.get("snaketracker_csrf")
    if token is None:
        raise RuntimeError("Demo browser session has no CSRF token.")
    return str(token)


def _post(
    client: TestClient,
    path: str,
    data: dict[str, str],
    *,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> str:
    response = client.post(
        path,
        data={"csrf_token": _csrf(client), **data},
        files=files,
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise RuntimeError(
            f"Demo seed request {path} failed with {response.status_code}: {response.text[:500]}"
        )
    return str(response.headers.get("location", ""))


def _register_animal(
    client: TestClient, *, key: str, animal_type: str, name: str, species: str, notes: str
) -> str:
    location = _post(
        client,
        "/animals",
        {
            "idempotency_key": f"demo-animal-{key}",
            "animal_type": animal_type,
            "name": name,
            "species": species,
            "sex": "",
            "morph": "",
            "genetics": "",
            "birth_hatch_date": "",
            "acquisition_date": "",
            "breeder_source": "Fictional M6 demo collection",
            "notes": notes,
        },
    )
    _post(
        client,
        f"{location}/photo",
        {"idempotency_key": f"demo-photo-{key}"},
        files={"photo": (f"{key}.png", _profile_photo(key, name), "image/png")},
    )
    return location.rsplit("/", 1)[-1]


def _record_feeding(
    client: TestClient,
    animal_id: str,
    *,
    key: str,
    occurred: date,
    prey: str,
    size: str,
    weight: int,
    outcome: str,
    notes: str,
    inventory_id: str = "",
    inventory_version: str = "",
) -> None:
    _post(
        client,
        f"/animals/{animal_id}/feedings",
        {
            "idempotency_key": f"demo-feeding-{key}",
            "occurred_at": _form_time(occurred),
            "prey_type": prey,
            "prey_size": size,
            "prey_weight_grams": str(weight),
            "preparation_method": "frozen_thawed",
            "quantity": "1",
            "outcome": outcome,
            "notes": notes,
            "inventory_item_id": inventory_id,
            "inventory_expected_stream_version": inventory_version,
            "inventory_quantity": "1" if inventory_id else "",
        },
    )


def _record_measurement(
    client: TestClient,
    animal_id: str,
    *,
    kind: str,
    key: str,
    occurred: date,
    value: int,
    notes: str,
) -> None:
    field = "weight_grams" if kind == "weights" else "length_mm"
    _post(
        client,
        f"/animals/{animal_id}/{kind}",
        {
            "idempotency_key": f"demo-{kind}-{key}",
            "occurred_at": _form_time(occurred),
            field: str(value),
            "notes": notes,
        },
    )


def _schedule(
    client: TestClient,
    animal_id: str,
    *,
    kind: str,
    key: str,
    interval: int,
    override: date | None = None,
) -> None:
    _post(
        client,
        f"/animals/{animal_id}/care-schedule/{kind}",
        {
            "idempotency_key": f"demo-schedule-{key}",
            "expected_stream_version": "0",
            "enabled": "true",
            "interval_days": str(interval),
            "override_due_at": _form_time(override) if override else "",
        },
    )


def _event_id(database: Path, animal_id: str, event_type: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT event_id FROM domain_events WHERE stream_id=? AND event_type=? "
            "ORDER BY stream_version LIMIT 1",
            (animal_id, event_type),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"Demo event {event_type} was not stored.")
    return str(row[0])


def _require_page_text(response_text: str, *, page: str, expected: tuple[str, ...]) -> None:
    missing = tuple(value for value in expected if value not in response_text)
    if missing:
        raise RuntimeError(f"Demo {page} is missing expected keeper content: {missing!r}")


def _prepare_target(data_dir: Path) -> Path:
    resolved = data_dir.resolve()
    database = resolved / "snaketracker.sqlite3"
    if not database.is_file():
        raise FileNotFoundError(f"The promoted database does not exist: {database}")
    return database


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _reset_demo_household(database: Path, household_id: str) -> None:
    """Remove only disposable demo-owned state while retaining its trusted identity."""
    if household_id != DEMO_HOUSEHOLD_ID:
        raise RuntimeError("Demo reset refused a household outside the reserved demo identity.")
    attachment_rows: list[tuple[str, str]] = []
    staging_ids: list[str] = []
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        reserved = connection.execute(
            "SELECT count(*) FROM household_summaries WHERE household_id=?",
            (household_id,),
        ).fetchone()[0]
        if reserved != 1:
            raise RuntimeError("Reserved demo household is missing; reset refused.")
        attachment_rows = [
            (str(storage_key), str(media_type))
            for storage_key, media_type in connection.execute(
                "SELECT storage_key,media_type FROM attachment_versions WHERE household_id=?",
                (household_id,),
            )
        ]
        staging_ids = [
            str(staged_id)
            for (staged_id,) in connection.execute(
                "SELECT staged_attachment_id FROM attachment_staging WHERE household_id=?",
                (household_id,),
            )
        ]
        event_ids = [
            str(event_id)
            for (event_id,) in connection.execute(
                "SELECT event_id FROM domain_events WHERE household_id=? "
                "AND stream_type<>'household'",
                (household_id,),
            )
        ]
        job_ids = [
            str(job_id)
            for (job_id,) in connection.execute(
                "SELECT job_id FROM jobs WHERE household_id=?", (household_id,)
            )
        ]
        if job_ids:
            placeholders = ",".join("?" for _ in job_ids)
            connection.execute(
                f"DELETE FROM delivery_attempts WHERE job_id IN ({placeholders})", job_ids
            )
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            connection.execute(
                f"DELETE FROM event_subjects WHERE event_id IN ({placeholders})", event_ids
            )
        for (content_table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'global_search_fts_content_g_%'"
        ).fetchall():
            content = str(content_table)
            fts = content.replace("_content_g_", "_fts_g_")
            rowids = [
                int(rowid)
                for (rowid,) in connection.execute(
                    f"SELECT rowid FROM {_quoted_identifier(content)} WHERE household_id=?",
                    (household_id,),
                )
            ]
            if rowids:
                placeholders = ",".join("?" for _ in rowids)
                connection.execute(
                    f"DELETE FROM {_quoted_identifier(fts)} WHERE rowid IN ({placeholders})",
                    rowids,
                )

        connection.execute("DELETE FROM attachment_versions WHERE household_id=?", (household_id,))
        connection.execute("DELETE FROM attachment_staging WHERE household_id=?", (household_id,))
        preserved_tables = {
            "authorization_memberships",
            "household_summaries",
            "domain_events",
            "event_streams",
            "idempotency_operations",
            "attachment_staging",
            "attachment_versions",
            "backup_requests",
            "backup_runs",
        }
        tables = [
            str(name)
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            if table in preserved_tables:
                continue
            columns = {
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({_quoted_identifier(table)})")
            }
            if "household_id" in columns:
                connection.execute(
                    f"DELETE FROM {_quoted_identifier(table)} WHERE household_id=?",
                    (household_id,),
                )
        connection.execute(
            "DELETE FROM domain_events WHERE household_id=? AND stream_type<>'household'",
            (household_id,),
        )
        connection.execute(
            "DELETE FROM event_streams WHERE household_id=? AND stream_type<>'household'",
            (household_id,),
        )
        connection.execute(
            "DELETE FROM idempotency_operations WHERE household_id=? "
            "AND operation_scope<>'household.demo_provision'",
            (household_id,),
        )
        remaining_high_water = int(
            connection.execute(
                "SELECT coalesce(max(global_position),0) FROM domain_events"
            ).fetchone()[0]
        )
        connection.execute(
            "UPDATE projection_generations SET high_water_position=?",
            (remaining_high_water,),
        )
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("Demo reset failed SQLite integrity validation.")
        connection.commit()

    attachment_storage = LocalAttachmentStorage(database.parent / "attachments")
    for storage_key, media_type in attachment_rows:
        attachment_storage.discard_finalized(UUID(storage_key), media_type)
    for staged_id in staging_ids:
        attachment_storage.discard_staged(UUID(staged_id))
    (database.parent / "demo-manifest.json").unlink(missing_ok=True)


def _rebuild_product_projections(database: Path) -> None:
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        manager = SQLiteProjectionGenerationManager(engine, product_projection_registry)
        for group in ("search", "insights", "dashboard"):
            manager.rebuild(group)
    finally:
        engine.dispose()


def _login(client: TestClient) -> None:
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if token is None:
        raise RuntimeError("Demo login page did not contain a CSRF token.")
    response = client.post(
        "/login",
        data={
            "csrf_token": token.group(1),
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
        },
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise RuntimeError(f"Demo login failed with {response.status_code}.")


def _stored_result(manifest_path: Path, database: Path, household_id: str) -> DemoSeedResult | None:
    if not manifest_path.is_file():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("scenario_version") != DEMO_SCENARIO_VERSION:
        raise RuntimeError("Existing demo manifest uses a conflicting scenario version.")
    with sqlite3.connect(database) as connection:
        actual = connection.execute(
            "SELECT count(*) FROM animal_current WHERE household_id=?", (household_id,)
        ).fetchone()[0]
    if actual != data.get("animal_count"):
        raise RuntimeError("Existing demo manifest conflicts with the promoted database.")
    return DemoSeedResult(
        scenario_version=str(data["scenario_version"]),
        database=str(data["database"]),
        as_of=str(data["as_of"]),
        household_id=str(data["household_id"]),
        animal_count=int(data["animal_count"]),
        enclosure_count=int(data["enclosure_count"]),
        snake_count=int(data["snake_count"]),
        spider_count=int(data["spider_count"]),
        lizard_count=int(data["lizard_count"]),
        scorpion_count=int(data["scorpion_count"]),
        profile_photo_count=int(data["profile_photo_count"]),
        event_count=int(data["event_count"]),
        prediction_ready=tuple(data["prediction_ready"]),
        insufficient_history_animals=tuple(data["insufficient_history_animals"]),
        animal_ids={str(key): str(value) for key, value in data["animal_ids"].items()},
    )


def _store_result(
    manifest_path: Path,
    database: Path,
    household_id: str,
    qualification_date: date,
    animals: dict[str, str],
) -> DemoSeedResult:
    with sqlite3.connect(database) as connection:
        event_count = int(
            connection.execute(
                "SELECT count(*) FROM domain_events WHERE household_id=?", (household_id,)
            ).fetchone()[0]
        )
        photo_count = int(
            connection.execute(
                "SELECT count(*) FROM attachment_versions WHERE household_id=?", (household_id,)
            ).fetchone()[0]
        )
    result = DemoSeedResult(
        scenario_version=DEMO_SCENARIO_VERSION,
        database=str(database),
        as_of=qualification_date.isoformat(),
        household_id=household_id,
        animal_count=13,
        enclosure_count=11,
        snake_count=4,
        spider_count=3,
        lizard_count=3,
        scorpion_count=3,
        profile_photo_count=photo_count,
        event_count=event_count,
        prediction_ready=("Ember", "Juniper", "Nova", "Onyx", "Pearl", "Sol"),
        insufficient_history_animals=("Bramble", "Cobalt", "Pip"),
        animal_ids=animals,
    )
    manifest = asdict(result)
    manifest["scenario_hash"] = hashlib.sha256(
        json.dumps(
            {
                "scenario_version": DEMO_SCENARIO_VERSION,
                "as_of": result.as_of,
                "animals": sorted(animals),
                "event_count": event_count,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _recover_completed_dataset(
    database: Path,
    settings: Settings,
    household_id: str,
    qualification_date: date,
    manifest_path: Path,
) -> DemoSeedResult:
    """Finalize an exactly complete dataset after verification was interrupted."""
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT name, animal_id, animal_type FROM animal_current WHERE household_id=?",
            (household_id,),
        ).fetchall()
        animals = {str(name): str(animal_id) for name, animal_id, _kind in rows}
        animal_types = [str(kind) for _name, _animal_id, kind in rows]
        shape = (
            set(animals) == DEMO_ANIMAL_NAMES,
            animal_types.count("snake") == 4,
            animal_types.count("spider") == 3,
            animal_types.count("lizard") == 3,
            animal_types.count("scorpion") == 3,
            connection.execute(
                "SELECT count(*) FROM enclosure_current WHERE household_id=?", (household_id,)
            ).fetchone()[0]
            == 11,
            connection.execute(
                "SELECT count(*) FROM attachment_versions WHERE household_id=?", (household_id,)
            ).fetchone()[0]
            == 13,
            connection.execute(
                "SELECT count(*) FROM domain_events WHERE household_id=?", (household_id,)
            ).fetchone()[0]
            >= 175,
        )
    if not all(shape):
        raise RuntimeError(
            "Partial demo data exists without a verified manifest; refusing changes."
        )

    app = build_application(settings)
    try:
        with TestClient(app) as client:
            _login(client)
            _verify_keeper_pages(client, animals, qualification_date)
    finally:
        app.state.database_engine.dispose()
    return _store_result(manifest_path, database, household_id, qualification_date, animals)


def _verify_keeper_pages(
    client: TestClient, animals: dict[str, str], qualification_date: date
) -> None:
    home = client.get("/home")
    home_expectations = ["13 animals", "11 enclosures"]
    if qualification_date == datetime.now(UTC).date():
        home_expectations.extend(("Overdue", "Due today", "Upcoming"))
    _require_page_text(home.text, page="Today page", expected=tuple(home_expectations))
    _require_page_text(
        client.get("/reports/care").text,
        page="care report",
        expected=("Juniper", "Ember", "Sol", "Onyx"),
    )
    _require_page_text(
        client.get("/reports/expenses").text,
        page="expense report",
        expected=("Feeders", "Habitat", "48.50", "78.25"),
    )
    _require_page_text(
        client.get("/search?q=moonlit").text,
        page="search",
        expected=("Moonlit Forest Vivarium", "Juniper", "2 results"),
    )
    analytics_expectations = {
        "Juniper": ("Feeding estimate", "Shed estimate"),
        "Ember": ("Feeding estimate", "Molt estimate"),
        "Nova": ("Feeding estimate", "Shed estimate"),
        "Pearl": ("Feeding estimate", "Molt estimate"),
        "Pip": ("Not enough history yet",),
        "Sol": ("Feeding estimate",),
        "Bramble": ("Not enough history yet",),
        "Onyx": ("Feeding estimate", "Molt estimate"),
        "Cobalt": ("Not enough history yet",),
    }
    for name, expected in analytics_expectations.items():
        response = client.get(f"/animals/{animals[name]}/analytics")
        if response.status_code != 200:
            raise RuntimeError(f"Demo analytics for {name} failed with {response.status_code}.")
        _require_page_text(response.text, page=f"{name} analytics", expected=expected)


def seed_demo(
    data_dir: Path,
    *,
    as_of: date | None = None,
    runtime_secret: str = DEMO_RUNTIME_SECRET,
    reset_existing: bool = False,
) -> DemoSeedResult:
    """Populate the reserved household in an existing promoted local database."""
    qualification_date = as_of or datetime.now(UTC).date()
    database = _prepare_target(data_dir)
    settings = Settings(
        environment=Environment.TEST,
        database_path=database,
        attachment_storage_path=database.parent / "attachments",
        backup_storage_path=database.parent / "backups",
        runtime_secret=SecretStr(runtime_secret),
        session_cookie_secure=False,
    )
    provisioned = provision_demo_household(settings, password=DEMO_PASSWORD)
    manifest_path = database.parent / "demo-manifest.json"
    if reset_existing:
        _reset_demo_household(database, str(provisioned.household_id))
    stored = _stored_result(manifest_path, database, str(provisioned.household_id))
    if stored is not None:
        return stored
    with sqlite3.connect(database) as connection:
        partial_animals = connection.execute(
            "SELECT count(*) FROM animal_current WHERE household_id=?",
            (str(provisioned.household_id),),
        ).fetchone()[0]
    if partial_animals:
        return _recover_completed_dataset(
            database,
            settings,
            str(provisioned.household_id),
            qualification_date,
            manifest_path,
        )
    app = build_application(settings)
    with TestClient(app) as client:
        _login(client)

        animals = {
            "Juniper": _register_animal(
                client,
                key="juniper",
                animal_type="snake",
                name="Juniper",
                species="Python regius",
                notes="Fictional demo snake; searches for moonlit cork hide.",
            ),
            "Atlas": _register_animal(
                client,
                key="atlas",
                animal_type="snake",
                name="Atlas",
                species="Boa imperator",
                notes="Fictional demo snake; searches for copper canopy.",
            ),
            "Ember": _register_animal(
                client,
                key="ember",
                animal_type="spider",
                name="Ember",
                species="Tliltocatl albopilosus",
                notes="Fictional demo spider; searches for velvet burrow.",
            ),
            "Pip": _register_animal(
                client,
                key="pip",
                animal_type="spider",
                name="Pip",
                species="Avicularia avicularia",
                notes="New fictional demo spider with deliberately limited history.",
            ),
            "Nova": _register_animal(
                client,
                key="nova",
                animal_type="snake",
                name="Nova",
                species="Lampropeltis getula",
                notes="Fictional demo kingsnake with prediction-ready care history.",
            ),
            "Cedar": _register_animal(
                client,
                key="cedar",
                animal_type="snake",
                name="Cedar",
                species="Python regius",
                notes="Fictional demo ball python with varied accepted feedings.",
            ),
            "Pearl": _register_animal(
                client,
                key="pearl",
                animal_type="spider",
                name="Pearl",
                species="Grammostola pulchripes",
                notes="Fictional demo spider with prediction-ready molt history.",
            ),
            "Sol": _register_animal(
                client,
                key="sol",
                animal_type="lizard",
                name="Sol",
                species="Pogona vitticeps",
                notes="Established fictional lizard; searches for sunstone ledge.",
            ),
            "Bramble": _register_animal(
                client,
                key="bramble",
                animal_type="lizard",
                name="Bramble",
                species="Correlophus ciliatus",
                notes="New fictional lizard with deliberately limited history.",
            ),
            "Dune": _register_animal(
                client,
                key="dune",
                animal_type="lizard",
                name="Dune",
                species="Eublepharis macularius",
                notes="Fictional lizard with bath, misting, and measurement records.",
            ),
            "Onyx": _register_animal(
                client,
                key="onyx",
                animal_type="scorpion",
                name="Onyx",
                species="Heterometrus spinifer",
                notes="Established fictional scorpion; searches for deep burrow.",
            ),
            "Cobalt": _register_animal(
                client,
                key="cobalt",
                animal_type="scorpion",
                name="Cobalt",
                species="Pandinus imperator",
                notes="New fictional scorpion with deliberately limited history.",
            ),
            "Saffron": _register_animal(
                client,
                key="saffron",
                animal_type="scorpion",
                name="Saffron",
                species="Hadrurus arizonensis",
                notes="Fictional desert scorpion with concise care history.",
            ),
        }

        enclosures: dict[str, str] = {}
        for key, name, enclosure_type, notes in (
            ("forest", "Moonlit Forest Vivarium", "vivarium", "Searchable cork hide habitat."),
            ("canopy", "Copper Canopy Habitat", "terrarium", "Searchable climbing habitat."),
            ("burrow", "Velvet Burrow", "terrarium", "Searchable deep substrate habitat."),
            ("nursery", "Obsidian Nursery", "terrarium", "Searchable juvenile spider habitat."),
            ("nova", "Nova Stone Terrarium", "terrarium", "Fictional kingsnake habitat."),
            ("cedar", "Cedar Hollow Vivarium", "vivarium", "Fictional ball python habitat."),
            ("sunstone", "Sunstone Lizard Ledge", "vivarium", "Searchable lizard habitat."),
            ("bramble", "Bramble Nursery", "vivarium", "Fictional juvenile lizard habitat."),
            ("dune", "Dune Ridge Habitat", "terrarium", "Fictional arid lizard habitat."),
            ("onyx", "Onyx Deep Burrow", "terrarium", "Searchable scorpion habitat."),
            ("saffron", "Saffron Desert Habitat", "terrarium", "Fictional arid scorpion habitat."),
        ):
            location = _post(
                client,
                "/enclosures",
                {
                    "idempotency_key": f"demo-enclosure-{key}",
                    "name": name,
                    "enclosure_type": enclosure_type,
                    "notes": notes,
                },
            )
            enclosures[key] = location.rsplit("/", 1)[-1]

        for key, animal_name, enclosure_key, occurred in (
            ("juniper-first", "Juniper", "canopy", qualification_date - timedelta(days=200)),
            ("juniper-current", "Juniper", "forest", qualification_date - timedelta(days=90)),
            ("atlas", "Atlas", "canopy", qualification_date - timedelta(days=120)),
            ("ember-first", "Ember", "nursery", qualification_date - timedelta(days=210)),
            ("ember-current", "Ember", "burrow", qualification_date - timedelta(days=110)),
            ("pip", "Pip", "nursery", qualification_date - timedelta(days=20)),
            ("nova", "Nova", "nova", qualification_date - timedelta(days=170)),
            ("cedar", "Cedar", "cedar", qualification_date - timedelta(days=130)),
            ("pearl", "Pearl", "burrow", qualification_date - timedelta(days=210)),
            ("sol-first", "Sol", "bramble", qualification_date - timedelta(days=220)),
            ("sol-current", "Sol", "sunstone", qualification_date - timedelta(days=100)),
            ("bramble", "Bramble", "bramble", qualification_date - timedelta(days=18)),
            ("dune", "Dune", "dune", qualification_date - timedelta(days=140)),
            ("onyx-first", "Onyx", "nursery", qualification_date - timedelta(days=230)),
            ("onyx-current", "Onyx", "onyx", qualification_date - timedelta(days=115)),
            ("cobalt", "Cobalt", "onyx", qualification_date - timedelta(days=25)),
            ("saffron", "Saffron", "saffron", qualification_date - timedelta(days=160)),
        ):
            _post(
                client,
                f"/animals/{animals[animal_name]}/enclosure",
                {
                    "idempotency_key": f"demo-assignment-{key}",
                    "enclosure_id": enclosures[enclosure_key],
                    "occurred_at": _form_time(occurred),
                    "notes": "Fictional demo rehousing record.",
                },
            )

        inventory: dict[str, str] = {}
        for key, name, quantity in (
            ("mice", "Demo frozen mice", 30),
            ("crickets", "Demo feeder crickets", 40),
        ):
            location = _post(
                client,
                "/inventory",
                {
                    "idempotency_key": f"demo-inventory-{key}",
                    "name": name,
                    "unit": "item",
                    "reorder_threshold": "5",
                },
            )
            item_id = location.rsplit("/", 1)[-1]
            _post(
                client,
                f"/inventory/{item_id}/receive",
                {
                    "idempotency_key": f"demo-inventory-receive-{key}",
                    "expected_stream_version": "1",
                    "quantity": str(quantity),
                    "reference": "Fictional owner-review stock receipt",
                },
            )
            inventory[key] = item_id

        juniper_feedings = _dates_from_intervals(
            qualification_date - timedelta(days=4), (10, 11, 9, 10, 12, 10, 9, 11, 10)
        )
        for index, occurred in enumerate(juniper_feedings):
            _record_feeding(
                client,
                animals["Juniper"],
                key=f"juniper-{index}",
                occurred=occurred,
                prey="mouse",
                size="small adult",
                weight=18 + index,
                outcome="accepted",
                notes=f"Demo crescent feeding note {index + 1}.",
                inventory_id=inventory["mice"] if index == len(juniper_feedings) - 1 else "",
                inventory_version="2" if index == len(juniper_feedings) - 1 else "",
            )
        _record_feeding(
            client,
            animals["Juniper"],
            key="juniper-refused",
            occurred=qualification_date - timedelta(days=38),
            prey="mouse",
            size="small adult",
            weight=22,
            outcome="refused",
            notes="Demo refusal after a quiet evening.",
        )
        target = _event_id(database, animals["Juniper"], "animal.feeding_recorded")
        _post(
            client,
            f"/animals/{animals['Juniper']}/events/{target}/correct",
            {
                "idempotency_key": "demo-feeding-juniper-correction",
                "occurred_at": _form_time(juniper_feedings[0]),
                "prey_type": "mouse",
                "prey_size": "small adult",
                "prey_weight_grams": "17",
                "preparation_method": "frozen_thawed",
                "quantity": "1",
                "outcome": "accepted",
                "notes": "Corrected fictional prey weight from keeper note.",
            },
        )

        for index, days_ago in enumerate((180, 145, 110, 75, 40, 8)):
            _record_measurement(
                client,
                animals["Juniper"],
                kind="weights",
                key=f"juniper-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=410 + index * 24,
                notes="Fictional calm weight check.",
            )
        for index, days_ago in enumerate((175, 130, 90, 50, 10)):
            _record_measurement(
                client,
                animals["Juniper"],
                kind="lengths",
                key=f"juniper-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=780 + index * 32,
                notes="Fictional relaxed length measurement.",
            )
        juniper_sheds = _dates_from_intervals(
            qualification_date - timedelta(days=15), (44, 48, 46, 50, 45)
        )
        for index, occurred in enumerate(juniper_sheds):
            _post(
                client,
                f"/animals/{animals['Juniper']}/sheds",
                {
                    "idempotency_key": f"demo-shed-juniper-{index}",
                    "occurred_at": _form_time(occurred),
                    "blue_state": "false",
                    "completed": "true",
                    "result": "complete",
                    "notes": "Fictional complete one-piece shed.",
                },
            )
        for index, days_ago in enumerate((120, 30)):
            _post(
                client,
                f"/animals/{animals['Juniper']}/baths",
                {
                    "idempotency_key": f"demo-bath-juniper-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_minutes": "15",
                    "reason": "Fictional hydration observation",
                    "notes": "Calm supervised demo soak.",
                },
            )

        ember_feedings = _dates_from_intervals(
            qualification_date - timedelta(days=6), (14, 15, 13, 16, 14, 15, 14)
        )
        for index, occurred in enumerate(ember_feedings):
            _record_feeding(
                client,
                animals["Ember"],
                key=f"ember-{index}",
                occurred=occurred,
                prey="cricket",
                size="medium",
                weight=2,
                outcome="accepted",
                notes=f"Demo lantern feeding note {index + 1}.",
                inventory_id=inventory["crickets"] if index == len(ember_feedings) - 1 else "",
                inventory_version="2" if index == len(ember_feedings) - 1 else "",
            )
        for index, days_ago in enumerate((68, 34)):
            _record_feeding(
                client,
                animals["Ember"],
                key=f"ember-refused-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="cricket",
                size="medium",
                weight=2,
                outcome="refused",
                notes="Fictional premolt refusal.",
            )
        for index, days_ago in enumerate((190, 150, 110, 70, 35, 7)):
            _record_measurement(
                client,
                animals["Ember"],
                kind="weights",
                key=f"ember-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=34 + index * 3,
                notes="Fictional spider weight check.",
            )
        ember_molts = _dates_from_intervals(
            qualification_date - timedelta(days=25), (58, 63, 60, 62, 59)
        )
        for index, occurred in enumerate(ember_molts):
            _post(
                client,
                f"/animals/{animals['Ember']}/molts",
                {
                    "idempotency_key": f"demo-molt-ember-{index}",
                    "occurred_at": _form_time(occurred),
                    "result": "complete",
                    "notes": "Fictional intact molt recorded for analytics.",
                },
            )
        _post(
            client,
            f"/animals/{animals['Ember']}/premolt-observations",
            {
                "idempotency_key": "demo-premolt-ember",
                "occurred_at": _form_time(qualification_date - timedelta(days=32)),
                "observed": "true",
                "notes": "Fictional darkened abdomen and reduced appetite.",
            },
        )

        for index, days_ago in enumerate((12, 3)):
            _record_feeding(
                client,
                animals["Pip"],
                key=f"pip-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="fruit fly culture",
                size="small",
                weight=1,
                outcome="accepted",
                notes="Limited fictional history for the insufficient-sample state.",
            )

        bulk_history = {
            "Atlas": ("mouse", "small adult", 18, 9),
            "Nova": ("mouse", "small adult", 19, 10),
            "Cedar": ("mouse", "small adult", 21, 12),
            "Pearl": ("roach", "medium", 3, 16),
        }
        for animal_name, (prey, size, weight, interval_days) in bulk_history.items():
            key_name = animal_name.casefold()
            for index in range(7):
                occurred = qualification_date - timedelta(days=(6 - index) * interval_days + 2)
                _record_feeding(
                    client,
                    animals[animal_name],
                    key=f"{key_name}-history-{index}",
                    occurred=occurred,
                    prey=prey,
                    size=size,
                    weight=weight + index % 3,
                    outcome="accepted",
                    notes=f"Fictional {animal_name} historical feeding {index + 1}.",
                )

        sol_feedings = _dates_from_intervals(
            qualification_date - timedelta(days=3), (4, 5, 4, 6, 5, 4)
        )
        for index, occurred in enumerate(sol_feedings):
            _record_feeding(
                client,
                animals["Sol"],
                key=f"sol-{index}",
                occurred=occurred,
                prey="dubia roach",
                size="medium",
                weight=3 + index % 2,
                outcome="accepted",
                notes="Fictional established lizard feeding.",
            )
        _record_feeding(
            client,
            animals["Sol"],
            key="sol-refused",
            occurred=qualification_date - timedelta(days=14),
            prey="dubia roach",
            size="medium",
            weight=4,
            outcome="refused",
            notes="Fictional lizard refusal retained outside estimate history.",
        )
        for index, days_ago in enumerate((120, 80, 40, 5)):
            _record_measurement(
                client,
                animals["Sol"],
                kind="weights",
                key=f"sol-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=310 + index * 18,
                notes="Fictional lizard weight trend.",
            )
        for index, days_ago in enumerate((150, 110, 70, 30, 4)):
            _record_measurement(
                client,
                animals["Sol"],
                kind="lengths",
                key=f"sol-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=390 + index * 12,
                notes="Fictional lizard length trend.",
            )
        _post(
            client,
            f"/animals/{animals['Sol']}/baths",
            {
                "idempotency_key": "demo-bath-sol",
                "occurred_at": _form_time(qualification_date - timedelta(days=9)),
                "duration_minutes": "10",
                "reason": "Fictional supervised hydration",
                "notes": "Fictional lizard bath record.",
            },
        )
        for index, days_ago in enumerate((5, 1)):
            _post(
                client,
                f"/animals/{animals['Sol']}/mistings",
                {
                    "idempotency_key": f"demo-misting-sol-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_seconds": "25",
                    "notes": "Fictional lizard misting record.",
                },
            )

        for index, days_ago in enumerate((9, 2)):
            _record_feeding(
                client,
                animals["Bramble"],
                key=f"bramble-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="cricket",
                size="small",
                weight=1,
                outcome="accepted",
                notes="Sparse fictional lizard history.",
            )
        _record_measurement(
            client,
            animals["Bramble"],
            kind="weights",
            key="bramble",
            occurred=qualification_date - timedelta(days=3),
            value=42,
            notes="First fictional weight.",
        )
        _record_measurement(
            client,
            animals["Bramble"],
            kind="lengths",
            key="bramble",
            occurred=qualification_date - timedelta(days=3),
            value=160,
            notes="First fictional length.",
        )

        for index, days_ago in enumerate((31, 20, 10, 2)):
            _record_feeding(
                client,
                animals["Dune"],
                key=f"dune-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="mealworm",
                size="medium",
                weight=2,
                outcome="accepted",
                notes="Fictional lizard care history.",
            )
        for index, days_ago in enumerate((70, 8)):
            _record_measurement(
                client,
                animals["Dune"],
                kind="weights",
                key=f"dune-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=58 + index * 7,
                notes="Fictional lizard weight.",
            )
            _record_measurement(
                client,
                animals["Dune"],
                kind="lengths",
                key=f"dune-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=190 + index * 8,
                notes="Fictional lizard length.",
            )
            _post(
                client,
                f"/animals/{animals['Dune']}/baths",
                {
                    "idempotency_key": f"demo-bath-dune-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_minutes": "8",
                    "reason": "Fictional supervised care",
                    "notes": "Fictional lizard bath.",
                },
            )
            _post(
                client,
                f"/animals/{animals['Dune']}/mistings",
                {
                    "idempotency_key": f"demo-misting-dune-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_seconds": "15",
                    "notes": "Fictional lizard misting.",
                },
            )

        onyx_feedings = _dates_from_intervals(
            qualification_date - timedelta(days=7), (12, 13, 11, 14, 12, 13)
        )
        for index, occurred in enumerate(onyx_feedings):
            _record_feeding(
                client,
                animals["Onyx"],
                key=f"onyx-{index}",
                occurred=occurred,
                prey="cricket",
                size="large",
                weight=2,
                outcome="accepted",
                notes="Fictional established scorpion feeding.",
            )
        _record_feeding(
            client,
            animals["Onyx"],
            key="onyx-refused",
            occurred=qualification_date - timedelta(days=19),
            prey="cricket",
            size="large",
            weight=2,
            outcome="refused",
            notes="Fictional premolt refusal.",
        )
        for index, days_ago in enumerate((200, 130, 65, 6)):
            _record_measurement(
                client,
                animals["Onyx"],
                kind="weights",
                key=f"onyx-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                value=28 + index * 4,
                notes="Fictional scorpion weight.",
            )
        for index, occurred in enumerate(
            _dates_from_intervals(qualification_date - timedelta(days=28), (70, 73, 71, 74, 72))
        ):
            _post(
                client,
                f"/animals/{animals['Onyx']}/molts",
                {
                    "idempotency_key": f"demo-molt-onyx-{index}",
                    "occurred_at": _form_time(occurred),
                    "result": "complete",
                    "notes": "Fictional scorpion molt recorded with neutral schema v2.",
                },
            )
        _post(
            client,
            f"/animals/{animals['Onyx']}/premolt-observations",
            {
                "idempotency_key": "demo-premolt-onyx",
                "occurred_at": _form_time(qualification_date - timedelta(days=36)),
                "observed": "true",
                "notes": "Fictional premolt observation.",
            },
        )
        for index, days_ago in enumerate((12, 2)):
            _post(
                client,
                f"/animals/{animals['Onyx']}/mistings",
                {
                    "idempotency_key": f"demo-misting-onyx-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_seconds": "18",
                    "notes": "Fictional scorpion enclosure misting.",
                },
            )

        for index, days_ago in enumerate((16, 4)):
            _record_feeding(
                client,
                animals["Cobalt"],
                key=f"cobalt-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="cricket",
                size="small",
                weight=1,
                outcome="accepted",
                notes="Sparse fictional scorpion history.",
            )
        _record_measurement(
            client,
            animals["Cobalt"],
            kind="weights",
            key="cobalt",
            occurred=qualification_date - timedelta(days=5),
            value=17,
            notes="First fictional scorpion weight.",
        )

        for index, days_ago in enumerate((46, 31, 17, 3)):
            _record_feeding(
                client,
                animals["Saffron"],
                key=f"saffron-{index}",
                occurred=qualification_date - timedelta(days=days_ago),
                prey="roach",
                size="medium",
                weight=2,
                outcome="accepted",
                notes="Fictional desert scorpion feeding.",
            )
        _record_measurement(
            client,
            animals["Saffron"],
            kind="weights",
            key="saffron",
            occurred=qualification_date - timedelta(days=6),
            value=24,
            notes="Fictional desert scorpion weight.",
        )
        _post(
            client,
            f"/animals/{animals['Saffron']}/molts",
            {
                "idempotency_key": "demo-molt-saffron",
                "occurred_at": _form_time(qualification_date - timedelta(days=50)),
                "result": "complete",
                "notes": "Single fictional scorpion molt.",
            },
        )
        for index, days_ago in enumerate((15, 1)):
            _post(
                client,
                f"/animals/{animals['Saffron']}/mistings",
                {
                    "idempotency_key": f"demo-misting-saffron-{index}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "duration_seconds": "12",
                    "notes": "Fictional light scorpion misting.",
                },
            )

        for index, occurred in enumerate(
            _dates_from_intervals(qualification_date - timedelta(days=18), (41, 43, 42, 44, 41))
        ):
            _post(
                client,
                f"/animals/{animals['Nova']}/sheds",
                {
                    "idempotency_key": f"demo-shed-nova-{index}",
                    "occurred_at": _form_time(occurred),
                    "blue_state": "false",
                    "completed": "true",
                    "result": "complete",
                    "notes": "Fictional Nova complete shed.",
                },
            )
        for index, occurred in enumerate(
            _dates_from_intervals(qualification_date - timedelta(days=22), (61, 64, 62, 63, 60))
        ):
            _post(
                client,
                f"/animals/{animals['Pearl']}/molts",
                {
                    "idempotency_key": f"demo-molt-pearl-{index}",
                    "occurred_at": _form_time(occurred),
                    "result": "complete",
                    "notes": "Fictional Pearl complete molt.",
                },
            )

        for key, enclosure_key, route, days_ago in (
            ("forest-clean", "forest", "cleanings", 20),
            ("forest-water", "forest", "water-changes", 2),
            ("burrow-clean", "burrow", "cleanings", 18),
            ("burrow-water", "burrow", "water-changes", 1),
        ):
            _post(
                client,
                f"/enclosures/{enclosures[enclosure_key]}/{route}",
                {
                    "idempotency_key": f"demo-{key}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "notes": "Fictional demo habitat maintenance.",
                },
            )
        _post(
            client,
            f"/animals/{animals['Ember']}/mistings",
            {
                "idempotency_key": "demo-misting-ember",
                "occurred_at": _form_time(qualification_date - timedelta(days=1)),
                "duration_seconds": "20",
                "notes": "Fictional light wall mist.",
            },
        )

        _schedule(
            client,
            animals["Atlas"],
            kind="weight",
            key="overdue",
            interval=30,
            override=qualification_date - timedelta(days=1),
        )
        _schedule(
            client,
            animals["Atlas"],
            kind="length",
            key="today",
            interval=30,
            override=qualification_date,
        )
        _schedule(
            client,
            animals["Atlas"],
            kind="bath",
            key="upcoming",
            interval=30,
            override=qualification_date + timedelta(days=1),
        )
        _schedule(client, animals["Juniper"], kind="feeding", key="juniper-feed", interval=10)
        _schedule(client, animals["Ember"], kind="molt", key="ember-molt", interval=60)
        _schedule(client, animals["Nova"], kind="feeding", key="nova-feed", interval=10)
        _schedule(client, animals["Pearl"], kind="molt", key="pearl-molt", interval=62)
        _schedule(client, animals["Sol"], kind="length", key="sol-length", interval=30)
        _schedule(client, animals["Dune"], kind="misting", key="dune-mist", interval=3)
        _schedule(client, animals["Onyx"], kind="feeding", key="onyx-feed", interval=12)
        _schedule(client, animals["Onyx"], kind="molt", key="onyx-molt", interval=72)
        _schedule(client, animals["Saffron"], kind="misting", key="saffron-mist", interval=4)

        expense_locations: list[str] = []
        for index, amount, category, payee, notes in (
            (1, "46.50", "Feeders", "Fictional Feeder Co.", "Demo prey stock receipt."),
            (2, "78.25", "Habitat", "Fictional Habitat Shop", "Demo cork and substrate."),
            (3, "19.00", "Supplies", "Fictional Supply Desk", "Duplicate demo receipt."),
        ):
            expense_locations.append(
                _post(
                    client,
                    "/expenses",
                    {
                        "idempotency_key": f"demo-expense-{index}",
                        "amount": amount,
                        "currency": "USD",
                        "category": category,
                        "payee": payee,
                        "reference": f"DEMO-{index:03d}",
                        "notes": notes,
                        "occurred_at": _form_time(qualification_date - timedelta(days=20 - index)),
                    },
                )
            )
        expense_one = expense_locations[0].rsplit("/", 1)[-1]
        with sqlite3.connect(database) as connection:
            event_id = str(
                connection.execute(
                    "SELECT event_id FROM domain_events WHERE stream_id=? ORDER BY stream_version",
                    (expense_one,),
                ).fetchone()[0]
            )
        _post(
            client,
            f"/expenses/{expense_one}/correct",
            {
                "idempotency_key": "demo-expense-correction",
                "expected_stream_version": "1",
                "target_event_id": event_id,
                "amount": "48.50",
                "currency": "USD",
                "category": "Feeders",
                "payee": "Fictional Feeder Co.",
                "reference": "DEMO-001",
                "reason": "Fictional receipt total correction.",
            },
        )
        expense_three = expense_locations[2].rsplit("/", 1)[-1]
        with sqlite3.connect(database) as connection:
            event_id = str(
                connection.execute(
                    "SELECT event_id FROM domain_events WHERE stream_id=? ORDER BY stream_version",
                    (expense_three,),
                ).fetchone()[0]
            )
        _post(
            client,
            f"/expenses/{expense_three}/void",
            {
                "idempotency_key": "demo-expense-void",
                "expected_stream_version": "1",
                "target_event_id": event_id,
                "reason": "Fictional duplicate receipt.",
            },
        )

        if reset_existing:
            _rebuild_product_projections(database)
        _verify_keeper_pages(client, animals, qualification_date)
    app.state.database_engine.dispose()

    return _store_result(
        manifest_path,
        database,
        str(provisioned.household_id),
        qualification_date,
        animals,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "runtime" / "phase2")
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--runtime-secret-file", type=Path)
    parser.add_argument(
        "--reset-existing-demo",
        action="store_true",
        help="Replace only the reserved fictional demo household before seeding.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_secret = DEMO_RUNTIME_SECRET
    if args.runtime_secret_file is not None:
        runtime_secret = args.runtime_secret_file.read_text(encoding="utf-8").strip()
    result = seed_demo(
        args.data_dir,
        as_of=args.as_of,
        runtime_secret=runtime_secret,
        reset_existing=args.reset_existing_demo,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
