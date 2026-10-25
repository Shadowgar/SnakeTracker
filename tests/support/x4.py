"""Disposable X4 browser fixtures: keeper observations, never husbandry recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.browser.test_multispecies_workflow import (
    _assign,
    _create_enclosure,
    _csrf,
    _register,
)
from tests.support.inventory import inventory_feeding_fields


@dataclass(frozen=True)
class FrogFixture:
    animal_url: str
    enclosure_url: str | None = None
    inventory_url: str | None = None


def past_observation() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


def submit_observation(client, animal_url, route, values, *, key):
    page = client.get(animal_url)
    response = client.post(
        f"{animal_url}/{route}",
        data={
            "csrf_token": _csrf(page.text),
            "idempotency_key": key,
            "occurred_at": past_observation(),
            **values,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


def create_observed_cricket_stock(client: TestClient, *, key="x4-crickets") -> str:
    page = client.get("/inventory/new")
    response = client.post(
        "/inventory",
        data={
            "csrf_token": _csrf(page.text),
            "idempotency_key": key,
            "inventory_type": "food",
            "name": "Keeper-observed cricket stock",
            "food_category": "insect",
            "food_type": "cricket",
            "size_stage": "small",
            "preparation_method": "",
            "unit_code": "each",
            "starting_quantity": "10",
            "reorder_threshold": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def record_observed_feeding(client, animal_url, *, outcome, key):
    return submit_observation(
        client,
        animal_url,
        "feedings",
        {
            **inventory_feeding_fields(client, animal_url),
            "outcome": outcome,
            "notes": f"Keeper observed {outcome} outcome; synthetic qualification record.",
        },
        key=key,
    )


def save_schedule(client, animal_url, kind, *, key, interval="7"):
    page = client.get(animal_url)
    response = client.post(
        f"{animal_url}/care-schedule/{kind}",
        data={
            "csrf_token": _csrf(page.text),
            "idempotency_key": key,
            "expected_stream_version": "0",
            "enabled": "true",
            "interval_days": interval,
            "override_due_at": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


def seed_frog(client: TestClient, *, with_care=False) -> FrogFixture:
    """Seed Fern through ordinary authenticated routes; client must already be signed in.

    with_care=True also creates an enclosure, explicit cricket stock, one observed feeding,
    fractional measurements, and keeper-selected reminders for browser screenshot fixtures.
    The caller supplies a disposable application's TestClient and retains its DB for serving.
    """
    animal = _register(client, "Fern", "amphibian", "Keeper-entered frog")
    if not with_care:
        return FrogFixture(animal)
    enclosure = _create_enclosure(client, "Fern enclosure")
    _assign(client, animal, enclosure, "x4-seed-placement")
    inventory = create_observed_cricket_stock(client)
    record_observed_feeding(client, animal, outcome="accepted", key="x4-seed-feeding")
    submit_observation(
        client,
        animal,
        "weights",
        {"weight_grams": "12.375", "notes": "Observed mass"},
        key="x4-seed-weight",
    )
    submit_observation(
        client,
        animal,
        "lengths",
        {"length_value": "4.85", "length_unit": "cm"},
        key="x4-seed-length",
    )
    for kind in ("feeding", "weight", "length", "cleaning", "water_change"):
        save_schedule(client, animal, kind, key=f"x4-seed-schedule-{kind}")
    return FrogFixture(animal, enclosure, inventory)
