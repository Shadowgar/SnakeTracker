from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from snaketracker.presentation import web


def test_animal_agenda_row_links_to_registered_care_form_and_today_return() -> None:
    animal_id = uuid4()
    animal = SimpleNamespace(
        animal_id=animal_id,
        name="Nyx",
        current_enclosure_id=None,
        care_action_keys=("feeding", "weight"),
    )
    item = SimpleNamespace(
        subject_type="animal",
        subject_id=animal_id,
        status="due_today",
        reminder_type="feeding",
        explanation="Every 10 days",
    )

    row = web._agenda_rows((item,), animals=(animal,), enclosures=())["due_today"][0]

    assert row["action_url"] == f"/animals/{animal_id}/feedings/new?return_to=today"
    assert row["action_label"] == "Record feeding"


def test_care_return_context_rejects_arbitrary_redirect_values() -> None:
    animal_id = str(uuid4())

    assert web._care_return_location(animal_id, "today") == "/home"
    assert web._care_return_location(animal_id, "https://attacker.invalid") == (
        f"/animals/{animal_id}"
    )
    assert web._care_return_location(animal_id, "//attacker.invalid") == f"/animals/{animal_id}"
