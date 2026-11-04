"""Smart Care session recovery keeps signed steps and keeper-entered values usable."""

import html
import re
from datetime import datetime

import pytest
from sqlalchemy import text

from tests.browser.test_multispecies_workflow import _client, _csrf, _setup
from tests.browser.test_smart_care import (
    _confirm,
    _count,
    _edit_token,
    _preview,
    _record_real_feeding,
)
from tests.integration.test_x5_amphibian_guides import seed_reference_animals


@pytest.fixture
def care_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAKETRACKER_DATABASE_PATH", str(tmp_path / "mixed-browser.sqlite3"))
    monkeypatch.setenv("SNAKETRACKER_ENVIRONMENT", "test")
    monkeypatch.setenv("SNAKETRACKER_ATTACHMENT_STORAGE_PATH", str(tmp_path / "attachments"))
    monkeypatch.setenv("SNAKETRACKER_BACKUP_STORAGE_PATH", str(tmp_path / "backups"))
    monkeypatch.setenv("SNAKETRACKER_REFERENCE_IMAGE_STORAGE_PATH", str(tmp_path / "references"))
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        yield client, animal


def _field(page, name):
    match = re.search(r'name="' + re.escape(name) + r'"[^>]*value="([^"]*)"', page.text)
    assert match is not None, (name, page.status_code)
    return html.unescape(match[1])


def _fields(edit, **changes):
    return {
        "csrf_token": _csrf(edit.text),
        "edit_token": _edit_token(edit),
        "choice": _field(edit, "choice"),
        "applicability": "true",
        "interval_days": "19",
        "first_due_at": "2026-12-09T14:37:12.123456",
        **changes,
    }


@pytest.mark.parametrize("choice", ["manual", "rvc-white-2024-feeding_interval-juvenile"])
def test_missing_csrf_cookie_edit_produces_usable_signed_form(care_client, choice):
    client, animal = care_client
    before = _count(client)
    previous_session = client.cookies["snaketracker_session"]
    client.cookies.delete("snaketracker_csrf")
    edit = client.get(f"{animal}/smart-care/feeding/edit", params={"choice": choice})
    assert edit.status_code == 200
    assert client.cookies["snaketracker_session"] != previous_session
    preview = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(edit))
    assert preview.status_code == 200, preview.text
    assert "Every 19 days" in preview.text
    assert "14:37:12.123456" in preview.text
    assert _count(client) == before
    assert _confirm(client, animal, preview).status_code == 303
    assert _count(client) == before + 1


def test_missing_csrf_cookie_preview_does_not_invalidate_confirmation(care_client):
    client, animal = care_client
    edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
    client.cookies.delete("snaketracker_csrf")
    before = _count(client)
    preview = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(edit))
    assert preview.status_code == 200, preview.text
    assert _count(client) == before
    assert _confirm(client, animal, preview).status_code == 303
    assert _count(client) == before + 1


def test_validation_error_preserves_choice_interval_date_and_applicability(care_client):
    client, animal = care_client
    choice = "rvc-white-2024-feeding_interval-juvenile"
    edit = client.get(f"{animal}/smart-care/feeding/edit", params={"choice": choice})
    fields = _fields(edit, interval_days="4000")
    before = _count(client)
    rejected = client.post(f"{animal}/smart-care/feeding/preview", data=fields)
    assert rejected.status_code == 422
    for name in ("choice", "interval_days", "first_due_at"):
        assert _field(rejected, name) == fields[name]
    assert re.search(r'name="applicability"[^>]*checked', rejected.text)
    assert _count(client) == before
    preview = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(rejected))
    assert preview.status_code == 200, preview.text


@pytest.mark.parametrize("cookie", ["present", "missing", "invalid"])
def test_csrf_rejection_preserves_edit_for_explicit_resubmission(care_client, cookie):
    client, animal = care_client
    edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
    if cookie != "present":
        client.cookies.delete("snaketracker_csrf")
    if cookie == "invalid":
        client.cookies.set("snaketracker_csrf", "untrusted")
    before = _count(client)
    rejected = client.post(
        f"{animal}/smart-care/feeding/preview", data=_fields(edit, csrf_token="untrusted")
    )
    assert rejected.status_code == 403
    assert _field(rejected, "interval_days") == "19"
    assert _field(rejected, "first_due_at") == "2026-12-09T14:37:12.123456"
    assert _count(client) == before
    preview = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(rejected))
    assert preview.status_code == 200, preview.text


def test_csrf_rejection_preserves_signed_confirmation_and_idempotency(care_client):
    client, animal = care_client
    preview = _preview(client, animal, interval="19", first_due="2026-12-09T14:37:12.123456")
    client.cookies.delete("snaketracker_csrf")
    before = _count(client)
    rejected = _confirm(client, animal, preview, csrf_token="untrusted")
    assert rejected.status_code == 403
    assert "Every 19 days" in rejected.text
    assert "14:37:12.123456" in rejected.text
    assert _count(client) == before
    for _ in range(2):
        assert _confirm(client, animal, rejected).status_code == 303
    assert _count(client) == before + 1
    with client.app.state.database_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM reminder_rule_current")).scalar_one() == 1
        )


@pytest.mark.parametrize("step", ["preview", "confirm"])
@pytest.mark.parametrize("token", ["", "tampered"])
def test_missing_or_tampered_signed_tokens_never_recover_into_usable_tokens(
    care_client, step, token
):
    client, animal = care_client
    edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
    preview = _preview(client, animal)
    before = _count(client)
    client.cookies.delete("snaketracker_csrf")
    if step == "preview":
        rejected = client.post(
            f"{animal}/smart-care/feeding/preview", data=_fields(edit, edit_token=token)
        )
    else:
        rejected = _confirm(client, animal, preview, preview_token=token)
    assert rejected.status_code == 422
    assert 'name="preview_token"' not in rejected.text
    assert 'name="edit_token"' not in rejected.text
    assert _count(client) == before


@pytest.mark.parametrize("origin", ["existing", "preview"])
@pytest.mark.parametrize("offset", ["-04:00", "-05:00"])
def test_missing_cookie_recovery_preserves_exact_dst_instant(care_client, origin, offset):
    client, animal = care_client
    with client.app.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE household_summaries SET timezone='America/New_York'"))
    exact_due = "2026-11-01T01:30:37.123456" + offset
    preview = _preview(client, animal, interval="13", first_due=exact_due)
    assert preview.status_code == 200
    if origin == "existing":
        assert _confirm(client, animal, preview).status_code == 303
        href = f"{animal}/smart-care/feeding/edit?choice=manual"
    else:
        href = html.unescape(re.search(r'<a href="([^"]+)">Edit again</a>', preview.text)[1])
    before = _count(client)
    client.cookies.delete("snaketracker_csrf")
    edit = client.get(href)
    assert edit.status_code == 200
    assert _field(edit, "interval_days") == "13"
    assert _field(edit, "first_due_at") == "2026-11-01T01:30:37.123"
    fields = _fields(edit, first_due_at=_field(edit, "first_due_at"))
    invalid = client.post(
        f"{animal}/smart-care/feeding/preview", data={**fields, "interval_days": "0"}
    )
    assert invalid.status_code == 422
    reviewed = client.post(
        f"{animal}/smart-care/feeding/preview",
        data=_fields(invalid, first_due_at=_field(invalid, "first_due_at")),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert f"UTC{offset}" in reviewed.text
    assert _count(client) == before
    assert _confirm(client, animal, reviewed).status_code == 303
    with client.app.state.database_engine.connect() as connection:
        due = connection.execute(
            text("SELECT override_due_at FROM reminder_rule_current")
        ).scalar_one()
    assert datetime.fromisoformat(due) == datetime.fromisoformat(exact_due)


def test_missing_applicability_is_preserved_as_unchecked(care_client):
    client, animal = care_client
    edit = client.get(
        f"{animal}/smart-care/feeding/edit?choice=rvc-white-2024-feeding_interval-juvenile"
    )
    rejected = client.post(
        f"{animal}/smart-care/feeding/preview", data=_fields(edit, applicability="")
    )
    assert rejected.status_code == 422
    assert _field(rejected, "interval_days") == "19"
    assert not re.search(r'name="applicability"[^>]*checked', rejected.text)


@pytest.mark.parametrize("step", ["preview", "confirm"])
def test_foreign_origin_cannot_recover_or_write(care_client, step):
    client, animal = care_client
    edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
    preview = _preview(client, animal)
    before = _count(client)
    session = client.cookies["snaketracker_session"]
    client.cookies.delete("snaketracker_csrf")
    fields = (
        _fields(edit)
        if step == "preview"
        else {
            "csrf_token": _csrf(preview.text),
            "preview_token": _field(preview, "preview_token"),
        }
    )
    route = f"feeding/{step}" if step == "preview" else step
    rejected = client.post(
        f"{animal}/smart-care/{route}", data=fields, headers={"origin": "https://untrusted.example"}
    )
    assert rejected.status_code == 403
    assert 'name="edit_token"' not in rejected.text
    assert 'name="preview_token"' not in rejected.text
    assert client.cookies["snaketracker_session"] == session
    assert "snaketracker_csrf" not in client.cookies
    assert _count(client) == before


@pytest.mark.parametrize("change", ["rule", "history"])
def test_stale_confirmation_retains_values_but_requires_fresh_preview(care_client, change):
    client, animal = care_client
    preview = _preview(client, animal, interval="19", first_due="2026-11-01T12:37:12.123456")
    if change == "rule":
        other = _preview(client, animal, interval="7")
        assert _confirm(client, animal, other).status_code == 303
    else:
        _record_real_feeding(client, animal, "stale-recovery-feeding")
    before = _count(client)
    rejected = _confirm(client, animal, preview)
    assert rejected.status_code == 422
    assert _field(rejected, "interval_days") == "19"
    assert _field(rejected, "first_due_at") == "2026-11-01T12:37:12.123"
    assert 'name="preview_token"' not in rejected.text
    assert _count(client) == before
    current = client.post(
        f"{animal}/smart-care/feeding/preview",
        data=_fields(rejected, first_due_at=_field(rejected, "first_due_at")),
    )
    assert current.status_code == 200, current.text
    assert _confirm(client, animal, current).status_code == 303
    with client.app.state.database_engine.connect() as connection:
        due = connection.execute(
            text("SELECT override_due_at FROM reminder_rule_current")
        ).scalar_one()
    assert datetime.fromisoformat(due) == datetime.fromisoformat("2026-11-01T12:37:12.123456+00:00")


def test_stale_edit_retains_values_but_requires_fresh_preview(care_client):
    client, animal = care_client
    edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
    other = _preview(client, animal, interval="7")
    assert _confirm(client, animal, other).status_code == 303
    before = _count(client)
    rejected = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(edit))
    assert rejected.status_code == 422
    assert _field(rejected, "interval_days") == "19"
    assert _field(rejected, "first_due_at") == "2026-12-09T14:37:12.123456"
    assert 'name="preview_token"' not in rejected.text
    assert _count(client) == before
    current = client.post(f"{animal}/smart-care/feeding/preview", data=_fields(rejected))
    assert current.status_code == 200, current.text
    assert _confirm(client, animal, current).status_code == 303


def test_csrf_recovery_after_refused_care_requires_new_preview(care_client):
    client, animal = care_client
    preview = _preview(client, animal, interval="19", first_due="2026-12-09T14:37:12.123456")
    _record_real_feeding(client, animal, "refused-after-preview", outcome="refused")
    before = _count(client)
    client.cookies.delete("snaketracker_csrf")
    rejected = _confirm(client, animal, preview, csrf_token="untrusted")
    assert rejected.status_code == 403
    assert 'name="preview_token"' not in rejected.text
    assert _field(rejected, "interval_days") == "19"
    assert _count(client) == before
    current = client.post(
        f"{animal}/smart-care/feeding/preview",
        data=_fields(rejected, first_due_at=_field(rejected, "first_due_at")),
    )
    assert current.status_code == 200, current.text
    assert _confirm(client, animal, current).status_code == 303
