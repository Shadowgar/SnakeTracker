from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def create_food_inventory(
    client: TestClient,
    *,
    name: str = "Small Frozen Mouse",
    quantity: str = "100",
    idempotency_prefix: str = "browser-food",
) -> str:
    """Create stocked structured Food through the same browser path keepers use."""
    form = client.get("/inventory/new")
    created = client.post(
        "/inventory",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": f"{idempotency_prefix}-create",
            "inventory_type": "food",
            "name": name,
            "food_category": "whole_prey",
            "food_type": "mouse",
            "size_stage": "small",
            "preparation_method": "frozen_thawed",
            "unit_code": "each",
            "reorder_threshold": "1",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text
    item_url = created.headers["location"]
    detail = client.get(item_url)
    received = client.post(
        f"{item_url}/receive",
        data={
            "csrf_token": _csrf(detail.text),
            "idempotency_key": f"{idempotency_prefix}-receive",
            "expected_stream_version": "1",
            "quantity": quantity,
            "reference": "Browser fixture stock",
        },
        follow_redirects=False,
    )
    assert received.status_code == 303, received.text
    return item_url


def feeding_inventory_reference(client: TestClient, animal_url: str) -> tuple[str, str]:
    """Return the CSRF token and current item/version reference from a feeding form."""
    form = client.get(f"{animal_url}/feedings/new")
    option = re.search(r'<option value="([0-9a-f-]+:\d+)"[^>]*>', form.text)
    assert option is not None, form.text
    return _csrf(form.text), option.group(1)


def inventory_feeding_fields(
    client: TestClient, animal_url: str, *, amount: str = "1"
) -> dict[str, str]:
    csrf, reference = feeding_inventory_reference(client, animal_url)
    return {
        "csrf_token": csrf,
        "inventory_item_id": reference,
        "inventory_quantity": amount,
    }
