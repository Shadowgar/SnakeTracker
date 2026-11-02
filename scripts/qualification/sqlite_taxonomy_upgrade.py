#!/usr/bin/env python3
"""Run the hardened 0023 -> 0025 regression against the actual runtime image.

Mount the checkout read-only at /qualification; run with /app as working directory.
No test dependencies, production volumes, secrets, providers or backup are needed.
"""

from __future__ import annotations

import json
import runpy
import sqlite3
import tempfile
from pathlib import Path

root = Path(__file__).parents[2]
check = runpy.run_path(root / "tests/integration/test_taxonomy_migration_runtime.py")[
    "check_hardened_upgrade"
]
print(json.dumps({"sqlite_version": sqlite3.sqlite_version}), flush=True)
with tempfile.TemporaryDirectory(prefix="taxonomy-sqlite-") as temporary:
    check(Path(temporary) / "runtime.db", Path.cwd())
print(json.dumps({"status": "passed", "schema": "0025_natural_history", "trusted_schema": 0}))
