from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from snaketracker.presentation import web

ZONE = ZoneInfo("UTC")
NOW = datetime(2026, 8, 25, 12, tzinfo=UTC)


def reminder(
    reminder_type: str,
    subject_type: str,
    subject_id: object,
    status: str,
    days: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        rule_id=uuid4(),
        reminder_type=reminder_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status=status,
        due_at=NOW + timedelta(days=days),
        source_occurred_at=NOW - timedelta(days=4),
        source_label="accepted feeding" if reminder_type == "feeding" else reminder_type,
        explanation="Fixture schedule",
    )


def animal(name: str, enclosure_id: object | None, animal_type: str = "snake") -> SimpleNamespace:
    return SimpleNamespace(
        animal_id=uuid4(),
        name=name,
        animal_type=animal_type,
        current_enclosure_id=enclosure_id,
        care_action_keys=("feeding", "misting"),
        photo_attachment_version_id=None,
    )


def test_friendly_due_language_covers_keeper_relative_ranges() -> None:
    assert web._friendly_due(NOW - timedelta(days=3), now=NOW, timezone=ZONE) == "3 days overdue"
    assert web._friendly_due(NOW - timedelta(days=1), now=NOW, timezone=ZONE) == "1 day overdue"
    assert web._friendly_due(NOW, now=NOW, timezone=ZONE) == "Due today"
    assert web._friendly_due(NOW + timedelta(days=1), now=NOW, timezone=ZONE) == "Due tomorrow"
    assert web._friendly_due(NOW + timedelta(days=4), now=NOW, timezone=ZONE) == "Due in 4 days"
    assert web._friendly_due(NOW + timedelta(days=9), now=NOW, timezone=ZONE) == "Due Sep 3"


def test_collection_rows_share_reminder_urgency_without_inventing_care() -> None:
    enclosure_id = uuid4()
    enclosure = SimpleNamespace(enclosure_id=enclosure_id, name="Habitat")
    atlas = animal("Atlas", enclosure_id)
    pip = animal("Pip", enclosure_id, "spider")
    nova = animal("Nova", None)
    rows = web._animal_collection_rows(
        (atlas, pip, nova),
        (
            reminder("feeding", "animal", atlas.animal_id, "upcoming", 3),
            reminder("cleaning", "enclosure", enclosure_id, "overdue", -2),
        ),
        enclosures=(enclosure,),
        timezone=ZONE,
        now=NOW,
    )

    assert rows[0]["care_status"] == "overdue"
    assert rows[1]["care_label"].startswith("Enclosure cleaning")
    assert rows[2]["care_label"] == "No care scheduled"
    assert rows[2]["enclosure_name"] is None


def test_enclosure_rows_present_occupancy_and_maintenance_states() -> None:
    occupied_id = uuid4()
    empty_id = uuid4()
    occupied = SimpleNamespace(enclosure_id=occupied_id, name="Occupied")
    empty = SimpleNamespace(enclosure_id=empty_id, name="Empty")
    keeper = animal("Keeper", occupied_id)
    rows = web._enclosure_collection_rows(
        (occupied, empty),
        (keeper,),
        (
            reminder("water_change", "enclosure", occupied_id, "due_today", 0),
            reminder("feeding", "animal", keeper.animal_id, "upcoming", 2),
        ),
        timezone=ZONE,
        now=NOW,
    )

    assert rows[0]["occupants"] == (keeper,)
    assert rows[0]["maintenance_status"] == "due_today"
    assert rows[1]["occupants"] == ()
    assert rows[1]["maintenance_label"] == "No care due"


def test_agenda_enclosure_actions_cover_single_shared_and_empty_habitats() -> None:
    single_id, shared_id, empty_id = uuid4(), uuid4(), uuid4()
    mistable = animal("Vesper", single_id, "spider")
    first = animal("First", shared_id)
    second = animal("Second", shared_id)
    enclosures = (
        SimpleNamespace(enclosure_id=single_id, name="Single"),
        SimpleNamespace(enclosure_id=shared_id, name="Shared"),
        SimpleNamespace(enclosure_id=empty_id, name="Empty"),
    )
    rows = web._agenda_rows(
        (
            reminder("misting", "enclosure", single_id, "due_today", 0),
            reminder("cleaning", "enclosure", shared_id, "overdue", -1),
            reminder("water_change", "enclosure", empty_id, "upcoming", 1),
        ),
        animals=(mistable, first, second),
        enclosures=enclosures,
        timezone=ZONE,
        now=NOW,
    )

    assert rows["due_today"][0]["action_label"] == "Mist"
    assert rows["overdue"][0]["subject_name"] == "Shared"
    assert rows["upcoming"][0]["action_label"] == "Change water"


def test_calendar_projection_handles_month_navigation_and_invalid_input() -> None:
    scheduled = reminder("feeding", "animal", uuid4(), "due_today", 0)
    scheduled_row = {"item": scheduled, "subject_name": "Atlas", "title": "Feeding"}
    completed_row = {"local_date": NOW.date(), "title": "Feeding", "subject_name": "Atlas"}
    result = web._calendar_view(
        month_value="2026-08",
        selected_value="invalid",
        scheduled_rows=(scheduled_row,),
        completed=(completed_row,),
        timezone=ZONE,
        now=NOW,
    )

    assert result["month_label"] == "August 2026"
    assert result["previous_month"] == "2026-07"
    assert result["next_month"] == "2026-09"
    assert result["selected_scheduled"] == (scheduled_row,)
    assert result["selected_completed"] == (completed_row,)
    selected_day = next(
        day for week in result["weeks"] for day in week if day["date"] == NOW.date()
    )
    assert selected_day["due_count"] == 1
    assert selected_day["overdue_count"] == 0
    assert selected_day["upcoming_count"] == 0
    assert web._month_date("not-a-month", NOW.date()).day == 1


def test_completed_calendar_rows_deduplicate_and_label_subject_streams() -> None:
    household_id = uuid4()
    enclosure_id = uuid4()
    atlas = animal("Atlas", enclosure_id)
    enclosure = SimpleNamespace(enclosure_id=enclosure_id, name="Habitat")

    def event(event_type: str, stream_type: str, stream_id: object) -> SimpleNamespace:
        return SimpleNamespace(
            event_id=uuid4(),
            event_type=event_type,
            stream_type=stream_type,
            stream_id=stream_id,
            stream_version=1,
            occurred_at=NOW,
            payload=object(),
            title="Care recorded",
            description="Completed care",
        )

    animal_event = event("animal.feeding_recorded", "animal", atlas.animal_id)
    other_event = event("animal.weight_recorded", "other", uuid4())
    ignored_animal_event = event("animal.registered", "animal", atlas.animal_id)
    enclosure_event = event("enclosure.cleaning_recorded", "enclosure", enclosure_id)
    ignored_enclosure_event = event("enclosure.registered", "enclosure", enclosure_id)
    animal_service = SimpleNamespace(
        effective_history=lambda _household_id, _animal_id: (
            animal_event,
            other_event,
            ignored_animal_event,
        )
    )
    enclosure_service = SimpleNamespace(
        effective_history=lambda _household_id, _enclosure_id: (
            enclosure_event,
            ignored_enclosure_event,
        )
    )

    rows = web._completed_care_rows(
        household_id=household_id,
        animals=(atlas,),
        enclosures=(enclosure,),
        animal_service=animal_service,
        enclosure_service=enclosure_service,
        timezone=ZONE,
    )

    assert {row["subject_name"] for row in rows} == {"Atlas", "Habitat", "Care"}
    assert any(row["subject_url"] == "/home" for row in rows)
    assert any(row["calendar_url"] == f"/animals/{atlas.animal_id}/timeline" for row in rows)
