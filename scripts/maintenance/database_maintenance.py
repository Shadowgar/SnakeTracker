#!/usr/bin/env python3
"""Run a bounded integrity check or passive WAL checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.maintenance import checkpoint_wal, quick_check


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("check", "checkpoint"))
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    database = args.database.resolve(strict=False)
    if not database.is_file():
        print("database must be an existing regular file", file=sys.stderr)
        return 2
    engine = create_sqlite_engine(database, require_local_storage=True)
    try:
        if args.operation == "check":
            result: dict[str, object] = {
                "database": str(database),
                "quick_check": quick_check(engine),
            }
        else:
            busy, log_pages, checkpointed_pages = checkpoint_wal(engine)
            result = {
                "busy": busy,
                "checkpointed_pages": checkpointed_pages,
                "database": str(database),
                "log_pages": log_pages,
                "mode": "PASSIVE",
            }
    finally:
        engine.dispose()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
