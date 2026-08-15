#!/usr/bin/env python3
"""Create the disposable, fictional M6 owner-review household."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[2]
DEMO_EMAIL = "owner@m6-demo.invalid"
DEMO_PASSWORD = "m6-demo-local-only-password"
DEMO_PORT = 18087
DEMO_SCENARIO_VERSION = "m6-owner-review.v1"
PHOTO_COLORS = {
    "juniper": (72, 112, 67),
    "atlas": (155, 103, 62),
    "ember": (157, 70, 45),
    "sable": (66, 60, 73),
    "pip": (61, 114, 126),
}


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    scenario_version: str
    database: str
    as_of: str
    animal_count: int
    snake_count: int
    spider_count: int
    profile_photo_count: int
    event_count: int
    prediction_ready: tuple[str, ...]
    insufficient_history_animal: str
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
    return token


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
    return response.headers.get("location", "")


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


def _prepare_target(data_dir: Path, *, replace: bool) -> Path:
    resolved = data_dir.resolve()
    if "demo" not in resolved.name.lower():
        raise ValueError("The owner-review data directory name must contain 'demo'.")
    database = resolved / "snaketracker.sqlite3"
    if database.exists() and not replace:
        raise FileExistsError(f"{database} already exists; use --replace for disposable demo data.")
    if replace:
        for child in (database, resolved / "attachments", resolved / "backups"):
            if child.is_dir():
                shutil.rmtree(child)
            elif child.exists():
                child.unlink()
    resolved.mkdir(parents=True, exist_ok=True)
    return database


def seed_demo(
    data_dir: Path, *, as_of: date | None = None, replace: bool = False
) -> DemoSeedResult:
    """Seed a separate M6 demo exclusively through authenticated application routes."""
    qualification_date = as_of or datetime.now(UTC).date()
    database = _prepare_target(data_dir, replace=replace)
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            attachment_storage_path=database.parent / "attachments",
            backup_storage_path=database.parent / "backups",
            runtime_secret="m6-owner-review-demo-runtime-secret",
            session_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        setup = client.get("/setup")
        token = re.search(r'name="csrf_token" value="([^"]+)"', setup.text)
        if token is None:
            raise RuntimeError("Demo setup page did not contain a CSRF token.")
        response = client.post(
            "/setup",
            data={
                "csrf_token": token.group(1),
                "household_name": "M6 Fictional Keeper Lab",
                "timezone": "UTC",
                "display_name": "Demo Keeper",
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "password_confirmation": DEMO_PASSWORD,
            },
            follow_redirects=False,
        )
        if response.status_code != 303:
            raise RuntimeError(f"Demo bootstrap failed with {response.status_code}.")

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
            "Sable": _register_animal(
                client,
                key="sable",
                animal_type="spider",
                name="Sable",
                species="Grammostola pulchra",
                notes="Fictional demo spider; searches for obsidian retreat.",
            ),
            "Pip": _register_animal(
                client,
                key="pip",
                animal_type="spider",
                name="Pip",
                species="Avicularia avicularia",
                notes="New fictional demo spider with deliberately limited history.",
            ),
        }

        enclosures: dict[str, str] = {}
        for key, name, enclosure_type, notes in (
            ("forest", "Moonlit Forest Vivarium", "vivarium", "Searchable cork hide habitat."),
            ("canopy", "Copper Canopy Habitat", "terrarium", "Searchable climbing habitat."),
            ("burrow", "Velvet Burrow", "terrarium", "Searchable deep substrate habitat."),
            ("nursery", "Obsidian Nursery", "terrarium", "Searchable juvenile spider habitat."),
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
            ("sable", "Sable", "burrow", qualification_date - timedelta(days=80)),
            ("pip", "Pip", "nursery", qualification_date - timedelta(days=20)),
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

        for key, enclosure_key, route, days_ago, extra in (
            ("forest-clean", "forest", "cleanings", 20, {}),
            ("forest-water", "forest", "water-changes", 2, {}),
            ("burrow-clean", "burrow", "cleanings", 18, {}),
            ("burrow-water", "burrow", "water-changes", 1, {}),
        ):
            _post(
                client,
                f"/enclosures/{enclosures[enclosure_key]}/{route}",
                {
                    "idempotency_key": f"demo-{key}",
                    "occurred_at": _form_time(qualification_date - timedelta(days=days_ago)),
                    "notes": "Fictional demo habitat maintenance.",
                    **extra,
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

        home = client.get("/home")
        home_expectations = ["5 animals", "4 enclosures"]
        if qualification_date == datetime.now(UTC).date():
            home_expectations.extend(("Overdue", "Due today", "Upcoming"))
        _require_page_text(
            home.text,
            page="Today page",
            expected=tuple(home_expectations),
        )
        care_report = client.get("/reports/care")
        _require_page_text(care_report.text, page="care report", expected=("Juniper", "Ember"))
        expense_report = client.get("/reports/expenses")
        _require_page_text(
            expense_report.text,
            page="expense report",
            expected=("Feeders", "Habitat", "48.50", "78.25"),
        )
        search = client.get("/search?q=moonlit")
        _require_page_text(
            search.text,
            page="search",
            expected=("Moonlit Forest Vivarium", "Juniper", "2 results"),
        )
        analytics_expectations = {
            "Juniper": ("feeding estimate", "shed estimate"),
            "Ember": ("feeding estimate", "molt estimate"),
            "Pip": ("Not enough history yet",),
        }
        for name, expected in analytics_expectations.items():
            response = client.get(f"/animals/{animals[name]}/analytics")
            if response.status_code != 200:
                raise RuntimeError(f"Demo analytics for {name} failed with {response.status_code}.")
            _require_page_text(response.text, page=f"{name} analytics", expected=expected)
    app.state.database_engine.dispose()

    with sqlite3.connect(database) as connection:
        event_count = int(connection.execute("SELECT count(*) FROM domain_events").fetchone()[0])
        photo_count = int(
            connection.execute("SELECT count(*) FROM attachment_versions").fetchone()[0]
        )
    result = DemoSeedResult(
        scenario_version=DEMO_SCENARIO_VERSION,
        database=str(database),
        as_of=qualification_date.isoformat(),
        animal_count=5,
        snake_count=2,
        spider_count=3,
        profile_photo_count=photo_count,
        event_count=event_count,
        prediction_ready=("Ember", "Juniper"),
        insufficient_history_animal="Pip",
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
    (database.parent / "demo-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "runtime" / "m6-owner-review-demo")
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = seed_demo(args.data_dir, as_of=args.as_of, replace=args.replace)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
