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
        assert item["image"].startswith("/static/animal-fallbacks/")
        assert item["description"] and item["benefit"]
    assert all(item["id"] not in {"x3", "amphibians"} for item in history["milestones"])


def test_deployment_records_must_be_confirmed_and_well_formed(tmp_path) -> None:
    path = tmp_path / "production-release-history.json"
    record = {
        "verified": True,
        "version": "1.2.3",
        "status": "deployed",
        "deployed_at": "2026-10-18T14:30:00-04:00",
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
    assert result[0]["date_label"] == "October 18, 2026"
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
