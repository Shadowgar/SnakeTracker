"""Updates copy and release ledger safety without touching production."""

from __future__ import annotations

import json

from snaketracker.presentation.updates import (
    confirmed_production_updates,
    development_history,
)


def test_full_merged_pr_history_is_accounted_for() -> None:
    history = development_history()
    assert len(history["milestones"]) == 16
    assert sorted({pr for item in history["milestones"] for pr in item["prs"]}) == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        20,
        22,
        23,
    ]
    assert sum(month["count"] for month in history["merge_activity"]) == 21
    for item in history["milestones"]:
        assert item["image"].startswith(
            ("/static/animal-fallbacks/", "/static/species-references/")
        )
        assert item["description"] and item["benefit"]
    assert all(item["id"] not in {"x3", "amphibians"} for item in history["milestones"])


def test_deployment_records_must_be_confirmed_and_well_formed(tmp_path) -> None:
    path = tmp_path / "production-release-history.json"
    record = {
        "verified": True,
        "version": "1.2.3",
        "status": "deployed",
        "deployed_at": "2026-10-17T14:30:00-04:00",
        "build_sha": "a" * 40,
        "title": "Better care history",
        "description": "A clear way to see your care records.",
        "changes": [{"kind": "Improved", "text": "Find your saved care notes more easily."}],
    }
    assert confirmed_production_updates(path) == ()
    path.write_text(json.dumps([{**record, "verified": False}, record]))
    result = confirmed_production_updates(path)
    assert len(result) == 1
    assert result[0]["title"] == "Better care history"
    assert result[0]["date_label"] == "October 17, 2026"
    path.write_text(json.dumps([record, {**record, "deployed_at": "2026-10-18"}]))
    assert len(confirmed_production_updates(path)) == 1
    path.write_text("{broken")
    assert confirmed_production_updates(path) == ()
    path.write_bytes(b"x" * (128 * 1024 + 1))
    assert confirmed_production_updates(path) == ()


def test_only_safe_release_values_are_accepted(tmp_path) -> None:
    path = tmp_path / "production-release-history.json"
    record = {
        "verified": True,
        "version": "1.0",
        "status": "rolled_back",
        "deployed_at": "2026-10-18T12:00:00Z",
        "build_sha": "b" * 40,
        "title": "Previous version restored",
        "description": "We restored the earlier version while checking a problem.",
        "changes": [{"kind": "Fixed", "text": "The earlier working version is back."}],
    }
    path.write_text(json.dumps([record, {**record, "status": "pending"}]))
    assert len(confirmed_production_updates(path)) == 1
    path.write_text(json.dumps([{**record, "changes": [{"kind": "New", "text": ""}]}]))
    assert confirmed_production_updates(path) == ()


def _release(**changes):
    return {
        "verified": True,
        "version": "1.2.3",
        "status": "deployed",
        "deployed_at": "2026-10-17T12:00:00Z",
        "build_sha": "a" * 40,
        "title": "Care made easier",
        "description": "Find your care records more easily.",
        "changes": [{"kind": "Improved", "text": "Clearer care history."}],
        **changes,
    }


def test_releases_sort_by_actual_instant_across_offsets(tmp_path):
    from datetime import UTC, datetime

    path = tmp_path / "releases.json"
    path.write_text(
        json.dumps(
            [
                _release(version="older", deployed_at="2026-10-17T22:00:00+10:00"),
                _release(version="newer", deployed_at="2026-10-17T15:00:00Z"),
            ]
        )
    )
    result = confirmed_production_updates(path, now=datetime(2026, 10, 20, tzinfo=UTC))
    assert [item["version"] for item in result] == ["newer", "older"]


def test_future_deployments_and_ambiguous_instants_do_not_claim_a_live_release(tmp_path):
    from datetime import UTC, datetime

    path = tmp_path / "releases.json"
    path.write_text(
        json.dumps(
            [
                _release(),
                _release(version="future", deployed_at="2026-10-21T12:00:00Z"),
                _release(build_sha="b" * 40),
            ]
        )
    )
    assert confirmed_production_updates(path, now=datetime(2026, 10, 20, tzinfo=UTC)) == ()


def test_rollback_remains_an_event_and_ledger_is_never_rewritten(tmp_path):
    from datetime import UTC, datetime

    path = tmp_path / "releases.json"
    path.write_text(
        json.dumps(
            [
                _release(version="2", deployed_at="2026-10-17T12:00:00Z"),
                _release(version="1", status="rolled_back", deployed_at="2026-10-18T12:00:00Z"),
            ]
        )
    )
    before = path.read_bytes()
    result = confirmed_production_updates(path, now=datetime(2026, 10, 20, tzinfo=UTC))
    assert [item["version"] for item in result] == ["1", "2"]
    assert result[0]["status"] == "rolled_back"
    assert path.read_bytes() == before
    assert confirmed_production_updates(path, now=datetime(2026, 10, 20, tzinfo=UTC)) == result


def test_stories_are_chronological_actionable_and_photos_are_credited():
    history = development_history()
    entries = history["milestones"]
    assert [item["date"] for item in entries] == sorted(
        (item["date"] for item in entries), reverse=True
    )
    for item in entries:
        assert item["action"] and item["details"]
        if item["image"].startswith("/static/species-references/"):
            assert item["credit"]["creator"]
            assert item["credit"]["license_code"] in {"cc0", "cc-by", "cc-by-sa"}
    assert {item["id"] for item in entries if item.get("featured")} == {"x1", "x2", "guides"}
