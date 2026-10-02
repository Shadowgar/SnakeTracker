from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.browser.test_animal_care_workflow import client_for, csrf_from, setup_and_sign_in
from tests.support.inventory import create_food_inventory, inventory_feeding_fields


class FormControls(HTMLParser):
    """Read the accessible action names and native semantics from rendered forms."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.controls: dict[str, tuple[str, dict[str, str | None]]] = {}
        self.forms: list[dict[str, str | None]] = []
        self._current: tuple[str, dict[str, str | None]] | None = None
        self._name: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "form":
            self.forms.append(dict(attrs))
        if tag in {"a", "button"}:
            self._current = (tag, dict(attrs))
            self._name = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._name.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None and tag == self._current[0]:
            self.controls[" ".join("".join(self._name).split())] = self._current
            self._current = None


@pytest.fixture
def keeper(tmp_path: Path) -> Iterator[TestClient]:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        yield client


def register_animal(client: TestClient, animal_type: str) -> str:
    form = client.get("/animals/new")
    created = client.post(
        "/animals",
        data={
            "csrf_token": csrf_from(form.text),
            "idempotency_key": f"form-actions-{animal_type}",
            "name": f"Action test {animal_type}",
            "animal_type": animal_type,
            "species": "Python regius" if animal_type == "snake" else "Grammostola pulchra",
            "sex": "unknown",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text
    return created.headers["location"]


def assert_navigation_action(controls: FormControls, name: str, href: str) -> None:
    tag, attrs = controls.controls[name]
    assert tag == "a", f"{name} must navigate without submitting the care form"
    assert attrs.get("href") == href
    assert {"button-link", "secondary-link"} <= set((attrs.get("class") or "").split()), (
        f"{name} must use the secondary button visual system"
    )
    assert "role" not in attrs and "tabindex" not in attrs


def assert_submit_action(controls: FormControls, name: str, action: str) -> None:
    tag, attrs = controls.controls[name]
    assert tag == "button" and attrs.get("type") == "submit"
    assert "secondary" not in (attrs.get("class") or "").split()
    assert any(
        form.get("action") == action and form.get("method") == "post" for form in controls.forms
    )


def test_empty_feeding_offers_primary_setup_and_secondary_navigation(keeper: TestClient) -> None:
    animal_url = register_animal(keeper, "snake")
    response = keeper.get(f"{animal_url}/feedings/new")
    assert response.status_code == 200
    controls = FormControls(response.text)
    tag, attrs = controls.controls["Add food to inventory"]
    assert tag == "a" and attrs.get("href") == "/inventory/new"
    assert "button-link" in (attrs.get("class") or "").split()
    assert "secondary-link" not in (attrs.get("class") or "").split()
    assert_navigation_action(controls, "Set up inventory", "/inventory")
    assert_navigation_action(controls, "Cancel", animal_url)
    assert "Record feeding" not in controls.controls


def test_each_record_form_has_primary_submit_and_button_styled_cancel(keeper: TestClient) -> None:
    snake_url = register_animal(keeper, "snake")
    spider_url = register_animal(keeper, "spider")
    create_food_inventory(keeper, idempotency_prefix="form-actions-food")
    for animal_url, route, kind in (
        (snake_url, "feedings", "feeding"),
        (snake_url, "weights", "weight"),
        (snake_url, "lengths", "length"),
        (snake_url, "sheds", "shed"),
        (snake_url, "baths", "bath"),
        (spider_url, "molts", "molt"),
        (spider_url, "premolt-observations", "premolt"),
        (spider_url, "mistings", "misting"),
    ):
        response = keeper.get(f"{animal_url}/{route}/new")
        assert response.status_code == 200, (kind, response.text)
        controls = FormControls(response.text)
        assert_navigation_action(controls, "Cancel", animal_url)
        assert_submit_action(controls, f"Record {kind}", f"{animal_url}/{route}")

    for context, destination in (("today", "/home"), ("care", f"{snake_url}/care")):
        response = keeper.get(f"{snake_url}/weights/new?return_to={context}")
        assert_navigation_action(FormControls(response.text), "Cancel", destination)


def test_applicable_corrections_and_deletions_keep_submit_and_navigation_semantics(
    keeper: TestClient,
) -> None:
    snake_url = register_animal(keeper, "snake")
    spider_url = register_animal(keeper, "spider")
    create_food_inventory(keeper, idempotency_prefix="correction-actions-food")
    occurred_at = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    for animal_url, route, event_type, values in (
        (snake_url, "feedings", "animal.feeding_recorded", {"outcome": "accepted"}),
        (snake_url, "weights", "animal.weight_recorded", {"weight_grams": "512.125"}),
        (
            snake_url,
            "lengths",
            "animal.length_recorded",
            {"length_value": "9.13", "length_unit": "in"},
        ),
        (
            snake_url,
            "sheds",
            "animal.shed_recorded",
            {"blue_state": "false", "completed": "true", "result": "complete"},
        ),
        (spider_url, "molts", "animal.molt_recorded", {"result": "complete"}),
    ):
        form = keeper.get(f"{animal_url}/{route}/new")
        feeding = inventory_feeding_fields(keeper, animal_url) if route == "feedings" else {}
        recorded = keeper.post(
            f"{animal_url}/{route}",
            data={
                "csrf_token": csrf_from(form.text),
                "idempotency_key": f"form-actions-record-{route}",
                "occurred_at": occurred_at,
                **values,
                **feeding,
            },
            follow_redirects=False,
        )
        assert recorded.status_code == 303, recorded.text
        with keeper.app.state.database_engine.connect() as connection:
            event_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events "
                    "WHERE stream_id=:animal_id AND event_type=:event_type"
                ),
                {"animal_id": animal_url.rsplit("/", 1)[-1], "event_type": event_type},
            ).scalar_one()
        correction_url = f"{animal_url}/events/{event_id}/correct"
        correction = keeper.get(correction_url)
        assert correction.status_code == 200, correction.text
        controls = FormControls(correction.text)
        assert_navigation_action(controls, "Cancel", f"{animal_url}/timeline")
        assert_submit_action(controls, "Save correction", correction_url)

        delete_url = f"{animal_url}/events/{event_id}/delete"
        deletion = keeper.get(delete_url)
        assert deletion.status_code == 200, deletion.text
        controls = FormControls(deletion.text)
        assert_navigation_action(controls, "Cancel", f"{animal_url}/timeline#record-{event_id}")
        assert_submit_action(controls, "Delete record", delete_url)
