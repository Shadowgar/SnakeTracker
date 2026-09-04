from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from snaketracker.presentation import web


def test_animal_agenda_row_links_to_registered_care_form_and_today_return() -> None:
    animal_id = uuid4()
    animal = SimpleNamespace(
        animal_id=animal_id,
        name="Nyx",
        current_enclosure_id=None,
        care_action_keys=("feeding", "weight"),
        photo_attachment_version_id=None,
    )
    item = SimpleNamespace(
        subject_type="animal",
        subject_id=animal_id,
        status="due_today",
        reminder_type="feeding",
        explanation="Every 10 days",
        due_at=datetime.now(UTC),
        source_occurred_at=None,
        source_label="accepted feeding",
    )

    now = datetime.now(UTC)
    row = web._agenda_rows(
        (item,),
        animals=(animal,),
        enclosures=(),
        timezone=ZoneInfo("UTC"),
        now=now,
    )["due_today"][0]

    assert row["action_url"] == f"/animals/{animal_id}/feedings/new?return_to=today"
    assert row["action_label"] == "Feed"
    assert row["calendar_url"] == f"/animals/{animal_id}/care"


def test_care_return_context_rejects_arbitrary_redirect_values() -> None:
    animal_id = str(uuid4())

    assert web._care_return_location(animal_id, "today") == "/home"
    assert web._care_return_location(animal_id, "https://attacker.invalid") == (
        f"/animals/{animal_id}"
    )
    assert web._care_return_location(animal_id, "//attacker.invalid") == f"/animals/{animal_id}"


def test_agenda_row_derives_source_copy_from_a_persisted_reminder_fact() -> None:
    animal_id = uuid4()
    animal = SimpleNamespace(
        animal_id=animal_id,
        name="Nyx",
        current_enclosure_id=None,
        care_action_keys=("feeding",),
        photo_attachment_version_id=None,
    )
    item = SimpleNamespace(
        subject_type="animal",
        subject_id=animal_id,
        status="upcoming",
        reminder_type="feeding",
        explanation="Every 10 days",
        due_at=datetime(2026, 8, 31, tzinfo=UTC),
        source_occurred_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    row = web._agenda_rows(
        (item,),
        animals=(animal,),
        enclosures=(),
        timezone=ZoneInfo("UTC"),
        now=datetime(2026, 8, 27, tzinfo=UTC),
        return_context="animal",
    )["upcoming"][0]

    assert row["last_context"] == "Last feeding Aug 21"
    assert row["action_url"] == f"/animals/{animal_id}/feedings/new?return_to=animal"
