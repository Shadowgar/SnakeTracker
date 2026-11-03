#!/usr/bin/env python3
"""Qualify X5 in an isolated container with checkout-mounted source and no network."""

from __future__ import annotations

import json
import runpy
import sqlite3
import tempfile
from pathlib import Path

root = Path(__file__).parents[2]
assert sqlite3.sqlite_version == "3.40.1", sqlite3.sqlite_version
check = runpy.run_path(root / "tests/integration/test_x5_migration_runtime.py")["check_x5_upgrade"]
with tempfile.TemporaryDirectory(prefix="x5-sqlite-") as temporary:
    check(Path(temporary) / "x5.sqlite3", root)
print(
    json.dumps(
        {
            "sqlite_version": sqlite3.sqlite_version,
            "trusted_schema": 0,
            "historical_guides": 6,
            "immutable_triggers": 6,
            "schema": "0026_amphibian_care_guides",
            "status": "passed",
        }
    )
)
