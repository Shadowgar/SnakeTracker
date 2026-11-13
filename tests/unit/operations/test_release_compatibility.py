"""Release exports describe compatibility without opening the keeper's database."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SOURCE_SHA = "a" * 40


def export(tmp_path, *, build_sha=SOURCE_SHA, seed="1", arguments=()):
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": seed,
        "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "keeper.sqlite3"),
    }
    environment.pop("SNAKETRACKER_BUILD_GIT_SHA", None)
    if build_sha is not None:
        environment["SNAKETRACKER_BUILD_GIT_SHA"] = build_sha
    # Block real side effects, including SQLite opening an existing database.
    # Imports may read package metadata; writing files or connecting is unnecessary.
    script = """
import os, runpy, sys
def forbid(event, args):
    if event in {"sqlite3.connect", "socket.connect", "subprocess.Popen"}:
        raise AssertionError("Release metadata attempted external access")
    if event == "open":
        mode, flags = args[1:3]
        if isinstance(mode, str) and any(char in mode for char in "wax+"):
            raise AssertionError("Release metadata attempted a file write")
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError("Release metadata attempted a file write")
sys.addaudithook(forbid)
sys.argv = ["release_compatibility", *sys.argv[1:]]
runpy.run_module("snaketracker.operations.release_compatibility", run_name="__main__")
"""
    return subprocess.run(
        [sys.executable, "-c", script, *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_export_is_deterministic_and_does_not_open_or_change_keeper_data(tmp_path):
    database = tmp_path / "keeper.sqlite3"
    database.write_bytes(b"keeper data must not be opened")
    first = export(tmp_path, seed="1")
    second = export(tmp_path, seed="42")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    assert database.read_bytes() == b"keeper data must not be opened"
    assert list(tmp_path.iterdir()) == [database]
    manifest = json.loads(first.stdout)
    assert manifest["application"]["build_git_sha"] == SOURCE_SHA
    assert manifest["application"]["build_identity_status"] == "declared"
    assert manifest["application"]["version"]
    assert manifest["runtime_requirements"]["python"] == "<3.14,>=3.13"
    assert manifest["runtime_requirements"]["minimum_sqlite"] == "3.35.0"


def test_manifest_separates_readable_events_registration_writes_and_migration(tmp_path):
    result = export(tmp_path)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    declarations = manifest["supported_contracts"]
    assert declarations["readable_profiles"] == [
        "snake.v1",
        "spider.v1",
        "lizard.v1",
        "scorpion.v1",
        "amphibian.v1",
    ]
    assert declarations["registration_writes"]["amphibian.v1"] == ["animal.registered", 3]
    assert declarations["registration_writes"]["snake.v1"] == ["animal.registered", 2]
    assert ["animal.registered", 1] in declarations["readable_event_contracts"]
    assert ["enclosure.plant_watering_recorded", 1] in declarations["readable_event_contracts"]
    assert declarations["backup_manifest_version"] == 1
    assert len(declarations["projection_requirements"]) == 9
    assert ["global_search_fts", 1, 5] in declarations["projection_requirements"]
    schema = manifest["relational_schema"]
    assert schema["current_version"] == 28
    assert schema["mutable_versions"] == [28]
    assert 27 in schema["migration_required_versions"]
    assert 28 not in schema["migration_required_versions"]
    assert manifest["event_writes"]["status"] == "partially_declared"
    assert manifest["plugin_compatibility"]["status"] == "unrecorded"
    assert manifest["downgrade_compatibility"]["status"] == "unrecorded"
    assert manifest["qualification"]["status"] == "not_asserted"


def test_missing_build_identity_is_explicit_and_can_be_required(tmp_path):
    result = export(tmp_path, build_sha=None)
    assert result.returncode == 0, result.stderr
    application = json.loads(result.stdout)["application"]
    assert application["build_git_sha"] is None
    assert application["build_identity_status"] == "unrecorded"
    required = export(tmp_path, build_sha=None, arguments=("--require-build-identity",))
    assert required.returncode == 2
    assert required.stdout == ""
    assert "required" in required.stderr


@pytest.mark.parametrize("invalid", ["a" * 7, "A" * 40, "secret-value-must-not-appear"])
def test_invalid_build_identity_is_rejected_without_echoing_environment(tmp_path, invalid):
    result = export(tmp_path, build_sha=invalid)
    assert result.returncode == 2
    assert result.stdout == ""
    assert invalid not in result.stderr
