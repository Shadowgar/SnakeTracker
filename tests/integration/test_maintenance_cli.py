from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine

ROOT = Path(__file__).parents[2]


def run_script(name: str, database: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / name), str(database)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def create_database(database: Path) -> None:
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE maintenance_probe (id INTEGER PRIMARY KEY)"))
    finally:
        engine.dispose()


def test_storage_verification_reports_measured_filesystem(tmp_path: Path) -> None:
    result = run_script("scripts/benchmarks/verify_storage.sh", tmp_path / "candidate.sqlite3")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "supported"
    assert payload["filesystem"]


def test_integrity_check_is_bounded_and_does_not_create_database(tmp_path: Path) -> None:
    database = tmp_path / "maintenance.sqlite3"
    missing = run_script("scripts/maintenance/check_database.sh", database)
    assert missing.returncode == 2
    assert database.exists() is False

    create_database(database)
    result = run_script("scripts/maintenance/check_database.sh", database)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["quick_check"] == "ok"


def test_checkpoint_command_reports_bounded_passive_result(tmp_path: Path) -> None:
    database = tmp_path / "checkpoint.sqlite3"
    create_database(database)

    result = run_script("scripts/maintenance/checkpoint_wal.sh", database)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "PASSIVE"
    assert payload["busy"] == 0
