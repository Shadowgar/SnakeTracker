"""Explicit offline Natural History review operations; dry run is the default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from snaketracker.application.natural_history import NaturalHistoryVersion
from snaketracker.infrastructure.database.engine import (
    create_readonly_sqlite_engine,
    create_sqlite_engine,
)
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository

MAX_BUNDLE_BYTES = 128 * 1024


def load_version(path: Path) -> NaturalHistoryVersion:
    if not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Natural History bundle missing or larger than 128 KiB.")
    with path.open("rb") as stream:
        data = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("Natural History bundle larger than 128 KiB.")
    return NaturalHistoryVersion.model_validate_json(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--apply", action="store_true")
    commands = parser.add_subparsers(dest="action", required=True)
    retain = commands.add_parser("retain")
    retain.add_argument("bundle", type=Path)
    select = commands.add_parser("select")
    select.add_argument("association")
    select.add_argument("version", type=int)
    select.add_argument("--sha256", required=True)
    select.add_argument("--development", action="store_true")
    withdraw = commands.add_parser("withdraw")
    withdraw.add_argument("association")
    for cmd in (select, withdraw):
        cmd.add_argument("--expected-revision", type=int, required=True)
        cmd.add_argument("--actor", required=True)
        cmd.add_argument("--reason", required=True)
    history = commands.add_parser("history")
    history.add_argument("taxon", type=UUID)
    args = parser.parse_args()
    item = load_version(args.bundle) if args.action == "retain" else None
    if not args.apply and args.action != "history":
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "action": args.action,
                    "content_sha256": item.digest if item else getattr(args, "sha256", None),
                }
            )
        )
        return
    if args.database is None or not args.database.is_absolute() or not args.database.is_file():
        parser.error("An explicit absolute existing migrated database is required.")
    readonly = create_readonly_sqlite_engine(args.database)
    try:
        with readonly.connect() as c:
            if (
                c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                != "0025_natural_history"
            ):
                parser.error(
                    "Natural History schema 0025 is required; this command never migrates."
                )
    finally:
        readonly.dispose()
    engine = (
        create_readonly_sqlite_engine(args.database)
        if args.action == "history"
        else create_sqlite_engine(args.database, require_local_storage=True)
    )
    try:
        repo = NaturalHistoryRepository(engine)
        if args.action == "retain":
            assert item is not None
            association, version = repo.retain(item)
            print(
                json.dumps(
                    {
                        "association": association,
                        "version": version,
                        "content_sha256": item.digest,
                        "published": False,
                    }
                )
            )
        elif args.action == "select":
            repo.select(
                (args.association, args.version),
                expected_revision=args.expected_revision,
                content_sha256=args.sha256,
                actor=args.actor,
                reason=args.reason,
                development=args.development,
            )
            print("Selection recorded; this is not a deployment.")
        elif args.action == "withdraw":
            repo.withdraw(
                args.association,
                expected_revision=args.expected_revision,
                actor=args.actor,
                reason=args.reason,
            )
            print("Withdrawal recorded; retained versions are preserved.")
        else:
            print(
                json.dumps(
                    {
                        "versions": [v.model_dump(mode="json") for v in repo.versions(args.taxon)],
                        "decisions": repo.decisions(args.taxon),
                    },
                    indent=2,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
