#!/usr/bin/env python3
"""Measure M6 product projections on the versioned laptop dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from scripts.fixtures.generate_representative_dataset import build_dataset, canonical_bytes
from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.search import SearchService
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.product_experience.projections import product_projection_registry
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.infrastructure.search.fts import SQLAlchemyFTSSearchRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]


def percentile(samples: list[float], fraction: float) -> float:
    if not samples:
        raise ValueError("At least one sample is required.")
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def summary(samples: list[float]) -> dict[str, float | int]:
    return {
        "count": len(samples),
        "median": statistics.median(samples),
        "p95": percentile(samples, 0.95),
        "max": max(samples),
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def run(database: Path, *, animal_count: int, samples: int) -> dict[str, Any]:
    dataset = build_dataset(animal_count=animal_count)
    if database.exists():
        database.unlink()
    database.parent.mkdir(parents=True, exist_ok=True)
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"m6-qualification-secret-32-bytes",
    ).bootstrap(
        BootstrapCommand(
            household_name="M6 Qualification Home",
            timezone=cast(str, dataset["timezone"]),
            owner_email="m6-qualification@example.test",
            owner_display_name="M6 Qualification Owner",
            password="correct horse battery staple",
            idempotency_key="m6-qualification-bootstrap",
            correlation_id=uuid4(),
        )
    )
    animals = AnimalService(SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine))
    seeded_at = time.perf_counter()
    for fixture in cast(list[dict[str, str]], dataset["animals"]):
        animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key=f"m6-qualification-{fixture['fixture_id']}",
                name=fixture["name"],
                species=fixture["species"],
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=fixture["notes"],
                animal_type=fixture["animal_type"],
            )
        )
    seed_seconds = time.perf_counter() - seeded_at
    manager = SQLiteProjectionGenerationManager(engine, product_projection_registry)
    rebuilds: list[dict[str, object]] = []
    peak_wal = 0
    for cache_state in cast(list[str], dataset["cache_states"]):
        for group in product_projection_registry.group_names:
            started = time.perf_counter()
            rebuilt = manager.rebuild(group)
            rebuilds.append(
                {
                    "cache_state": cache_state,
                    "group": group,
                    "duration_seconds": time.perf_counter() - started,
                    "high_water_position": rebuilt.high_water_position,
                }
            )
            peak_wal = max(peak_wal, _size(database.with_name(database.name + "-wal")))
    search = SearchService(SQLAlchemyFTSSearchRepository(engine, manager))
    search_ms: list[float] = []
    collection_ms: list[float] = []
    for index in range(samples):
        started = time.perf_counter()
        results = search.search(bootstrap.household_id, frozenset(), f"search note {index % 10}")
        search_ms.append((time.perf_counter() - started) * 1000)
        if not results:
            raise RuntimeError("Representative FTS query returned no authorized results.")
        started = time.perf_counter()
        profiles = animals.list_profiles(bootstrap.household_id)
        collection_ms.append((time.perf_counter() - started) * 1000)
        if len(profiles) != animal_count:
            raise RuntimeError("Representative collection read is incomplete.")
    with engine.connect() as connection:
        integrity = str(connection.execute(text("PRAGMA integrity_check")).scalar_one())
        foreign_key_violations = len(connection.execute(text("PRAGMA foreign_key_check")).all())
        event_count = int(
            connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one()
        )
        generation_count = int(
            connection.execute(text("SELECT count(*) FROM projection_generations")).scalar_one()
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    final_bytes = _size(database)
    filesystem = os.statvfs(database.parent)
    free_bytes = filesystem.f_bavail * filesystem.f_frsize
    result: dict[str, Any] = {
        "schema_version": 1,
        "classification": "M6 laptop Docker development qualification",
        "dataset": {
            "id": dataset["dataset_id"],
            "sha256": hashlib.sha256(canonical_bytes(dataset)).hexdigest(),
            "animal_count": animal_count,
            "event_count": event_count,
            "production_husbandry_guidance": dataset["production_husbandry_guidance"],
        },
        "environment": {
            "revision": os.environ.get("SNAKETRACKER_QUALIFICATION_REVISION", "unavailable"),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "filesystem": os.environ.get("SNAKETRACKER_FILESYSTEM", "development-local"),
            "cache_states": dataset["cache_states"],
            "encryption": "application-backups-enabled; benchmark-database-ephemeral",
        },
        "measurements": {
            "seed_seconds": seed_seconds,
            "rebuilds": rebuilds,
            "search_ms": summary(search_ms),
            "collection_ms": summary(collection_ms),
            "database_bytes": final_bytes,
            "peak_observed_wal_bytes": peak_wal,
            "free_bytes": free_bytes,
            "shadow_headroom_multiple": free_bytes / max(final_bytes, 1),
            "generation_count": generation_count,
            "integrity_check": integrity,
            "foreign_key_violations": foreign_key_violations,
            "max_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
    }
    result["targets"] = evaluate_targets(result)
    engine.dispose()
    return result


def evaluate_targets(result: dict[str, Any]) -> dict[str, bool]:
    measurements = cast(dict[str, Any], result["measurements"])
    dataset = cast(dict[str, Any], result["dataset"])
    return {
        "dataset_seeded": measurements["generation_count"] >= 6
        and dataset["event_count"] >= dataset["animal_count"],
        "all_rebuilds_under_30_seconds": all(
            item["duration_seconds"] <= 30 for item in measurements["rebuilds"]
        ),
        "search_p95_at_most_500_ms": measurements["search_ms"]["p95"] <= 500,
        "collection_p95_at_most_500_ms": measurements["collection_ms"]["p95"] <= 500,
        "memory_at_most_512_mib": measurements["max_rss_mib"] <= 512,
        "shadow_headroom_at_least_2x": measurements["shadow_headroom_multiple"] >= 2,
        "integrity_check_ok": measurements["integrity_check"] == "ok",
        "foreign_keys_ok": measurements["foreign_key_violations"] == 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--animals", type=int, default=100)
    parser.add_argument("--samples", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args.database.resolve(), animal_count=args.animals, samples=args.samples)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "results.json").write_text(rendered, encoding="utf-8")
    checksum = hashlib.sha256(rendered.encode()).hexdigest()
    (args.output_dir / "results.sha256").write_text(f"{checksum}  results.json\n", encoding="utf-8")
    print(rendered, end="")
    return 0 if all(cast(dict[str, bool], result["targets"]).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
