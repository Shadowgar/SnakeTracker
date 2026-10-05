"""Operator-only, reviewed Care Guide bundle validation and import."""

from __future__ import annotations

import argparse
from pathlib import Path

from snaketracker.application.care_guides import GuideBundle
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository

MAX_BUNDLE_BYTES = 1024 * 1024


def load_bundle(path: Path) -> GuideBundle:
    if not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Reviewed bundle is missing or exceeds the 1 MiB import limit.")
    return GuideBundle.model_validate_json(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or import reviewed global Care Guides")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write new guide versions atomically")
    arguments = parser.parse_args()
    bundle = load_bundle(arguments.bundle)
    print(
        f"Validated {len(bundle.guides)} reviewed guides and "
        f"{sum(len(guide.claims) for guide in bundle.guides)} sourced claims."
    )
    if not arguments.apply:
        return
    if arguments.database is None or not arguments.database.is_absolute():
        parser.error("--apply requires an explicit absolute --database path")
    if not arguments.database.is_file():
        parser.error("--database must already exist and be migrated")
    engine = create_sqlite_engine(arguments.database, require_local_storage=False)
    try:
        imported, identical = SQLAlchemyCareGuideRepository(engine).import_bundle(bundle)
    finally:
        engine.dispose()
    print(f"Imported {imported} guide versions; {identical} identical versions already present.")


if __name__ == "__main__":
    main()
