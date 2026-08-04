#!/usr/bin/env python3
"""Report the measured filesystem used by a candidate database path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from snaketracker.infrastructure.database.sqlite_profile import qualify_local_filesystem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    database = args.database.resolve(strict=False)
    qualification = qualify_local_filesystem(database)
    print(
        json.dumps(
            {
                "database_parent": str(database.parent),
                "filesystem": qualification.filesystem,
                "mount_point": str(qualification.mount_point),
                "status": "supported",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
