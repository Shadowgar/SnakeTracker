#!/usr/bin/env python3
"""Qualify populated schema 27 on actual SQLite 3.40.1 with a read-only checkout."""

from __future__ import annotations

import json
import runpy
import sqlite3
import tempfile
from pathlib import Path

root = Path(__file__).parents[2]
if sqlite3.sqlite_version != "3.40.1":
    raise RuntimeError(f"This qualification requires SQLite 3.40.1, got {sqlite3.sqlite_version}")
check = runpy.run_path(root / "tests/integration/test_bioactive_migration_runtime.py")[
    "check_bioactive_upgrade"
]
with tempfile.TemporaryDirectory(prefix="bioactive-sqlite-") as temporary:
    check(Path(temporary) / "runtime.sqlite3", root=root)
print(
    json.dumps(
        {
            "status": "passed",
            "sqlite_version": sqlite3.sqlite_version,
            "schema": "0027_bioactive_plant_care",
            "trusted_schema": 0,
            "populated_preservation": True,
            "foreign_keys_and_immutable_triggers": True,
            "unsafe_downgrade_blocked": True,
        }
    )
)
