from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _command_id(text: str) -> str:
    match = re.search(r'name="idempotency_key" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def _logout(client: TestClient) -> None:
    page = client.get("/more")
    response = client.post(
        "/logout", data={"csrf_token": csrf_from(page.text)}, follow_redirects=False
    )
    assert response.status_code == 303


def _register_isolated_household(client: TestClient) -> None:
    page = client.get("/register")
    response = client.post(
        "/register",
        data={
            "csrf_token": csrf_from(page.text),
            "idempotency_key": _command_id(page.text),
            "collection_name": "Quiet Household",
            "timezone": "UTC",
            "display_name": "Second Keeper",
            "email": "second@example.com",
            "password": "another correct horse battery staple",
            "password_confirmation": "another correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/onboarding"


def test_secondary_destinations_use_focused_responsive_presentations(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        inventory_form = client.get("/inventory/new")
        created = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(inventory_form.text),
                "idempotency_key": _command_id(inventory_form.text),
                "name": "Keeper test supply",
                "unit": "item",
                "reorder_threshold": "2",
            },
            follow_redirects=False,
        )
        item_url = created.headers["location"]
        inventory = client.get("/inventory")
        assert 'class="summary-strip inventory-summary"' in inventory.text
        assert "Needs attention" in inventory.text
        assert "Keeper test supply" in inventory.text
        adjust = client.get(f"{item_url}/adjust")
        assert adjust.status_code == 200
        assert '<h1 id="page-title">Adjust stock</h1>' in adjust.text
        assert 'name="quantity_delta"' in adjust.text

        expenses = client.get("/expenses")
        assert 'class="summary-strip expense-summary"' in expenses.text
        assert "$0.00" in expenses.text
        reports = client.get("/reports")
        assert 'class="report-dashboard"' in reports.text
        assert "Collection snapshot" in reports.text
        collection = client.get("/reports/collection")
        assert "Download CSV" in collection.text
        assert "No report records yet." in collection.text

        search = client.get("/search?q=keeper")
        assert search.status_code == 200
        system = client.get("/operations/jobs")
        assert "Operator view" in system.text
        assert "production email adapter" in system.text

        _logout(client)
        for path in ("/login", "/register", "/forgot-password"):
            page = client.get(path)
            assert page.status_code == 200
            assert "auth-intro" in page.text
            assert "auth-form" in page.text


def test_secondary_and_onboarding_routes_preserve_household_isolation(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        animal_form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(animal_form.text),
                "idempotency_key": _command_id(animal_form.text),
                "animal_type": "snake",
                "name": "Owner Isolation Animal",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "owner-only-search-marker",
            },
            follow_redirects=False,
        )
        assert animal.status_code == 303
        inventory_form = client.get("/inventory/new")
        inventory = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(inventory_form.text),
                "idempotency_key": _command_id(inventory_form.text),
                "name": "Owner Isolation Supply",
                "unit": "box",
                "reorder_threshold": "1",
            },
            follow_redirects=False,
        )
        assert inventory.status_code == 303
        expense_form = client.get("/expenses/new")
        expense = client.post(
            "/expenses",
            data={
                "csrf_token": csrf_from(expense_form.text),
                "idempotency_key": _command_id(expense_form.text),
                "amount": "18.25",
                "currency": "USD",
                "category": "Owner Isolation Cost",
                "payee": "Private Vendor",
                "reference": "",
                "occurred_at": (
                    datetime.now(ZoneInfo("America/New_York")) - timedelta(minutes=5)
                ).strftime("%Y-%m-%dT%H:%M"),
                "notes": "owner-only-expense-marker",
            },
            follow_redirects=False,
        )
        assert expense.status_code == 303

        _logout(client)
        _register_isolated_household(client)

        onboarding = client.get("/onboarding")
        assert "Quiet Household" in onboarding.text
        assert "Add your first animal" in onboarding.text
        assert "Owner Isolation Animal" not in onboarding.text
        home = client.get("/home")
        assert "Continue setup" in home.text
        for path in (
            "/inventory",
            "/expenses",
            "/reports/collection",
            "/search?q=owner-only",
            "/more",
        ):
            page = client.get(path)
            assert page.status_code == 200
            assert "Owner Isolation Animal" not in page.text
            assert "Owner Isolation Supply" not in page.text
            assert "Owner Isolation Cost" not in page.text
            if path.startswith("/search"):
                assert "No matches" in page.text
        account = client.get("/more")
        assert "Second Keeper" in account.text
        assert "Quiet Household" in account.text
