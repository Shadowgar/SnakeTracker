"""The operator ledger preserves confirmed releases without touching application data."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from snaketracker.operations.record_release import record_release
from snaketracker.presentation.updates import confirmed_production_updates


def entry(version="1", **changes):
    return {
        "version": version,
        "verified": True,
        "status": "deployed",
        "deployed_at": "2026-10-17T12:00:00Z",
        "build_sha": "a" * 40,
        "title": "Clearer care history",
        "description": "Find saved records more easily.",
        "changes": [{"kind": "Improved", "text": "Clearer care notes."}],
        **changes,
    }


def test_dry_run_does_not_create_any_persistent_files(tmp_path):
    ledger = tmp_path / "releases.json"
    assert record_release(ledger, entry()) == 1
    assert list(tmp_path.iterdir()) == []


def test_append_and_rollback_keep_prior_records_and_private_permissions(tmp_path):
    ledger = tmp_path / "releases.json"
    assert record_release(ledger, entry(), apply=True) == 1
    first = json.loads(ledger.read_text())[0]
    assert (
        record_release(
            ledger,
            entry("0.9", status="rolled_back", deployed_at="2026-10-17T13:00:00Z"),
            apply=True,
        )
        == 2
    )
    assert json.loads(ledger.read_text())[0] == first
    assert ledger.stat().st_mode & 0o777 == 0o600
    assert confirmed_production_updates(ledger)[0]["status"] == "rolled_back"


@pytest.mark.parametrize(
    "bad", [{"verified": False}, {"build_sha": "unknown"}, {"deployed_at": "2099-10-18T12:00:00Z"}]
)
def test_unverified_or_invalid_note_cannot_replace_existing_history(tmp_path, bad):
    ledger = tmp_path / "releases.json"
    record_release(ledger, entry(), apply=True)
    before = ledger.read_bytes()
    with pytest.raises(ValueError):
        record_release(ledger, entry("2", **bad), apply=True)
    assert ledger.read_bytes() == before


def test_invalid_existing_ledger_is_never_reset(tmp_path):
    ledger = tmp_path / "releases.json"
    ledger.write_text("{broken")
    with pytest.raises(ValueError):
        record_release(ledger, entry(), apply=True)
    assert ledger.read_text() == "{broken"


def test_competing_operator_appends_do_not_lose_a_release(tmp_path):
    ledger = tmp_path / "releases.json"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                record_release,
                ledger,
                entry(str(i), deployed_at=f"2026-10-17T1{i}:00:00Z"),
                apply=True,
            )
            for i in (1, 2)
        ]
        assert sorted(f.result() for f in futures) == [1, 2]
    assert {row["version"] for row in json.loads(ledger.read_text())} == {"1", "2"}


def test_duplicate_instant_is_not_silently_replaced(tmp_path):
    ledger = tmp_path / "releases.json"
    record_release(ledger, entry(), apply=True)
    before = ledger.read_bytes()
    with pytest.raises(ValueError):
        record_release(ledger, entry("2"), apply=True)
    assert ledger.read_bytes() == before


def test_operator_cli_requires_apply_and_reports_invalid_notes(tmp_path, monkeypatch, capsys):
    import sys

    from snaketracker.operations.record_release import main

    note = tmp_path / "note.json"
    note.write_text(json.dumps(entry()))
    ledger = tmp_path / "releases.json"
    args = ["record_release", str(note), "--ledger", str(ledger)]
    monkeypatch.setattr(sys, "argv", args)
    main()
    assert "Validated" in capsys.readouterr().out
    assert not ledger.exists()
    monkeypatch.setattr(sys, "argv", [*args, "--apply"])
    main()
    assert "Recorded" in capsys.readouterr().out
    before = ledger.read_bytes()
    note.write_text("{broken")
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert ledger.read_bytes() == before
