"""Explicit offline X2 operator workflow; never downloads or migrates a database."""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from snaketracker.application.local_taxonomy import GenerationSource
from snaketracker.infrastructure.database.engine import (
    create_readonly_sqlite_engine,
    create_sqlite_engine,
)
from snaketracker.infrastructure.taxonomy.archive import ArchiveLimits, read_archive
from snaketracker.infrastructure.taxonomy.catalog import (
    LocalTaxonomyCatalog,
    validate_generation_source,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline local taxonomy; requires an explicit migrated database"
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Apply the explicitly selected mutation"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("archive", type=Path)
    stage.add_argument("--provider", required=True)
    stage.add_argument("--label", required=True)
    stage.add_argument("--source-url", required=True)
    stage.add_argument(
        "--taxon-base-url", help="Qualified source URL base for other archive namespaces"
    )
    stage.add_argument("--retrieved-at", required=True, type=datetime.fromisoformat)
    stage.add_argument("--snapshot-at", type=datetime.fromisoformat)
    stage.add_argument("--sha256", required=True)
    stage.add_argument("--rights", required=True)
    for name in ("promote", "rollback", "cleanup"):
        action = commands.add_parser(name)
        action.add_argument("generation", type=UUID)
        if name in {"promote", "rollback"}:
            action.add_argument(
                "--max-revisions",
                type=int,
                default=10000,
                help="Qualified bound on concurrent published identity deltas",
            )
            action.add_argument(
                "--max-reconciliation-seconds",
                type=float,
                default=2.0,
                help="Qualified SQL work deadline; excludes lock/commit I/O",
            )
        if name == "cleanup":
            action.add_argument(
                "--keep",
                type=UUID,
                action="append",
                required=True,
                help="Explicit generations retained for rollback/backup policy",
            )
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--group")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("taxon", type=UUID)
    commands.add_parser("conflicts")
    decision = commands.add_parser("resolve-conflict")
    decision.add_argument("conflict", type=int)
    decision.add_argument("--decided-by", required=True)
    decision.add_argument("--reason", required=True)
    arguments = parser.parse_args()
    with ExitStack() as resources:
        _execute(arguments, parser, resources)


def _execute(
    arguments: argparse.Namespace, parser: argparse.ArgumentParser, resources: ExitStack
) -> None:
    mutating = arguments.action not in {"search", "resolve", "conflicts"}
    if arguments.action == "stage":
        limits = ArchiveLimits()
        if not arguments.archive.is_file() or arguments.archive.stat().st_size > limits.max_bytes:
            parser.error("Archive missing or outside the qualified compressed byte bound")
        directory = resources.enter_context(
            TemporaryDirectory(prefix="care-keeper-verified-taxonomy-")
        )
        verified = Path(directory) / "archive.zip"
        digest = hashlib.sha256()
        copied = 0
        # Copy and hash one bounded stream. Every parser reads these exact bytes,
        # even if the operator's original path is replaced or modified later.
        with arguments.archive.open("rb") as handle, verified.open("xb") as destination:
            while chunk := handle.read(1024 * 1024):
                copied += len(chunk)
                if copied > limits.max_bytes:
                    parser.error("Archive outside the qualified compressed byte bound")
                destination.write(chunk)
                digest.update(chunk)
        checksum = digest.hexdigest()
        if checksum != arguments.sha256:
            parser.error("Archive checksum does not match the expected SHA-256")
        arguments.archive = verified
        source = GenerationSource(
            arguments.label,
            arguments.provider,
            arguments.source_url,
            arguments.retrieved_at,
            arguments.snapshot_at,
            checksum,
            arguments.rights,
        )
        validate_generation_source(source)
        if not arguments.apply:
            count = sum(
                1
                for _ in read_archive(
                    arguments.archive,
                    provider=arguments.provider,
                    source_base_url=arguments.taxon_base_url,
                )
            )
            print(json.dumps({"validated_rows": count, "checksum": checksum, "applied": False}))
            return
    if mutating and not arguments.apply:
        parser.error("Mutation requires --apply")
    database = arguments.database
    if database is None or not database.is_absolute() or not database.is_file():
        parser.error(
            "Requires an explicit existing absolute --database path; migrations are separate"
        )
    engine = (
        create_sqlite_engine(database, require_local_storage=False)
        if mutating
        else create_readonly_sqlite_engine(database)
    )
    try:
        catalog = LocalTaxonomyCatalog(engine)
        if arguments.action == "stage":
            generation = catalog.begin_generation(source, imported_at=datetime.now(UTC))
            # A failed import remains staging. Existing active generation is never changed here.
            count = 0
            try:
                for batch in batched(
                    read_archive(
                        arguments.archive,
                        provider=arguments.provider,
                        source_base_url=arguments.taxon_base_url,
                    ),
                    500,
                    strict=False,
                ):
                    catalog.stage(generation, batch)
                    count += len(batch)
                catalog.validate_generation(generation)
            except Exception:
                print(
                    json.dumps(
                        {"generation": str(generation), "state": "staging", "validated_rows": count}
                    )
                )
                raise
            result: object = {"generation": str(generation), "state": "ready", "rows": count}
        elif arguments.action in {"promote", "rollback"}:
            catalog.promote(
                arguments.generation,
                max_revisions=arguments.max_revisions,
                max_seconds=arguments.max_reconciliation_seconds,
            )
            result = {"active_generation": str(arguments.generation)}
        elif arguments.action == "cleanup":
            catalog.cleanup(arguments.generation, retained_generations=set(arguments.keep))
            result = {"cleaned_generation": str(arguments.generation)}
        elif arguments.action == "search":
            result = [
                asdict(record) for record in catalog.search(arguments.query, group=arguments.group)
            ]
        elif arguments.action == "resolve":
            record = catalog.resolve(arguments.taxon)
            result = asdict(record) if record else None
        elif arguments.action == "conflicts":
            result = [asdict(conflict) for conflict in catalog.conflicts()]
        else:
            catalog.resolve_conflict(
                arguments.conflict, decided_by=arguments.decided_by, reason=arguments.reason
            )
            result = {"resolved_conflict": arguments.conflict}
        print(json.dumps(result, default=str, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
