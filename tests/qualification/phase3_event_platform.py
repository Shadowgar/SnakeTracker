"""Reproducible Phase 3 event-platform qualification in the laptop container."""

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
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    BootstrapResult,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.events.sqlite_snapshots import SQLAlchemySnapshotRepository
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    canonical_event_checksum,
    event_checksum,
)
from snaketracker.platform.events.registry import HOUSEHOLD_CONTRACTS, EventRegistry
from snaketracker.platform.events.snapshots import AggregateLoader, AggregateSnapshot
from snaketracker.platform.events.store import StreamKey
from snaketracker.platform.projections.definitions import (
    ProjectionDefinition,
    ProjectionRegistry,
)
from tests.support.synthetic_events import (
    SYNTHETIC_COUNTER_CONTRACT,
    SyntheticCounterChangedV2,
    SyntheticSubjectValidator,
)
from tests.support.synthetic_projections import FTSStrategy, OrdinaryCounterStrategy

ROOT = Path(__file__).parents[2]
DATASET_ID = "snaketracker-reference-v1-phase3-event-slice"
SYNTHETIC_STREAM_TYPE = "__snaketracker_test__.counter"
SYNTHETIC_EVENT_TYPE = "__snaketracker_test__.counter.changed"
GROUP = "__snaketracker_test__.qualification_group"
CATEGORIES = (
    (30, "feeding"),
    (15, "measurement"),
    (8, "shed"),
    (8, "cleaning"),
    (10, "health"),
    (6, "behavior"),
    (8, "inventory"),
    (5, "expense"),
    (4, "profile"),
    (3, "reminder"),
    (3, "document"),
)


def percentile(samples: list[float], percentage: float) -> float:
    if not samples:
        raise ValueError("At least one sample is required.")
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentage)))
    return ordered[index]


def category_for(index: int) -> str:
    bucket = index % 100
    boundary = 0
    for percentage, category in CATEGORIES:
        boundary += percentage
        if bucket < boundary:
            return category
    raise AssertionError("Representative event distribution must total 100 percent.")


def make_event(
    household_id: UUID,
    actor_id: UUID,
    stream_id: UUID,
    version: int,
    *,
    label: str,
) -> DomainEvent:
    now = datetime(2026, 8, 6, 16, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=household_id,
        stream_type=SYNTHETIC_STREAM_TYPE,
        stream_id=stream_id,
        stream_version=version,
        event_type=SYNTHETIC_EVENT_TYPE,
        schema_version=2,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key=f"qualification-{stream_id}-{version}",
        subjects=(EventSubject(SYNTHETIC_STREAM_TYPE, stream_id, "primary", 0),),
        title="Synthetic qualification event",
        description=None,
        payload=cast(EventPayload, SyntheticCounterChangedV2(version, label)),
        metadata={"source": "qualification"},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def initialize_database(
    database: Path,
) -> tuple[Engine, BootstrapResult, SQLAlchemyEventStore]:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    result = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"phase3-qualification-secret-32-bytes",
    ).bootstrap(
        BootstrapCommand(
            household_name="Qualification Home",
            timezone="UTC",
            owner_email="qualification@example.com",
            owner_display_name="Qualification Owner",
            password="correct horse battery staple",
            idempotency_key="phase3-qualification-bootstrap",
            correlation_id=uuid4(),
        )
    )
    registry = EventRegistry(
        (*HOUSEHOLD_CONTRACTS, SYNTHETIC_COUNTER_CONTRACT),
        allow_reserved_test_namespace=True,
    )
    store = SQLAlchemyEventStore(engine, registry, SyntheticSubjectValidator())
    return engine, result, store


def bulk_seed(
    database: Path,
    household_id: UUID,
    actor_id: UUID,
    *,
    target_events: int,
) -> dict[str, object]:
    started = time.perf_counter()
    maximum_wal = 0
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA wal_autocheckpoint=1000")
        connection.execute("PRAGMA journal_size_limit=268435456")
        current = int(connection.execute("SELECT count(*) FROM domain_events").fetchone()[0])
        remaining = target_events - current
        if remaining < 10_000:
            raise ValueError("Qualification target must leave room for the 10,000-event stream.")
        stream_count = 500
        versions = [10_000]
        other_total = remaining - versions[0]
        base, extra = divmod(other_total, stream_count - 1)
        versions.extend(base + (1 if index < extra else 0) for index in range(stream_count - 1))
        stream_ids = [UUID(int=10_000 + index) for index in range(stream_count)]
        now = "2026-08-06T16:00:00.000000+00:00"
        connection.executemany(
            "INSERT INTO event_streams "
            "(household_id,stream_type,stream_id,current_version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)",
            [
                (str(household_id), SYNTHETIC_STREAM_TYPE, str(stream_id), version, now, now)
                for stream_id, version in zip(stream_ids, versions, strict=True)
            ],
        )
        event_rows: list[tuple[object, ...]] = []
        subject_rows: list[tuple[object, ...]] = []
        sequence = 0
        for stream_id, stream_events in zip(stream_ids, versions, strict=True):
            for version in range(1, stream_events + 1):
                category = category_for(sequence)
                event_id = UUID(int=1_000_000_000 + sequence)
                correlation_id = UUID(int=2_000_000_000 + sequence)
                payload = {"label": f"{category} representative note", "value": sequence}
                subject = {
                    "subject_type": SYNTHETIC_STREAM_TYPE,
                    "subject_id": str(stream_id),
                    "relationship": "primary",
                    "display_order": 0,
                }
                canonical = {
                    "event_id": str(event_id),
                    "household_id": str(household_id),
                    "stream_type": SYNTHETIC_STREAM_TYPE,
                    "stream_id": str(stream_id),
                    "stream_version": version,
                    "event_type": SYNTHETIC_EVENT_TYPE,
                    "schema_version": 2,
                    "occurred_at": now,
                    "recorded_at": now,
                    "actor_user_id": str(actor_id),
                    "correlation_id": str(correlation_id),
                    "causation_id": None,
                    "idempotency_key": f"qualification-bulk-{sequence}",
                    "subjects": [subject],
                    "title": "Synthetic qualification event",
                    "description": None,
                    "payload": payload,
                    "metadata": {"source": "qualification"},
                    "notes": None,
                }
                checksum = canonical_event_checksum(canonical)
                event_rows.append(
                    (
                        str(event_id),
                        str(household_id),
                        SYNTHETIC_STREAM_TYPE,
                        str(stream_id),
                        version,
                        SYNTHETIC_EVENT_TYPE,
                        2,
                        now,
                        now,
                        str(actor_id),
                        str(correlation_id),
                        None,
                        f"qualification-bulk-{sequence}",
                        "Synthetic qualification event",
                        None,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        '{"source":"qualification"}',
                        None,
                        checksum,
                    )
                )
                subject_rows.append(
                    (str(event_id), SYNTHETIC_STREAM_TYPE, str(stream_id), "primary", 0)
                )
                sequence += 1
                if len(event_rows) == 10_000:
                    _flush_batch(connection, event_rows, subject_rows)
                    maximum_wal = max(
                        maximum_wal, _size(database.with_name(database.name + "-wal"))
                    )
        if event_rows:
            _flush_batch(connection, event_rows, subject_rows)
            maximum_wal = max(maximum_wal, _size(database.with_name(database.name + "-wal")))
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {
        "duration_seconds": time.perf_counter() - started,
        "inserted_events": remaining,
        "stream_count": stream_count,
        "long_stream_events": versions[0],
        "peak_observed_wal_bytes": maximum_wal,
    }


def _flush_batch(
    connection: sqlite3.Connection,
    event_rows: list[tuple[object, ...]],
    subject_rows: list[tuple[object, ...]],
) -> None:
    connection.executemany(
        "INSERT INTO domain_events "
        "(event_id,household_id,stream_type,stream_id,stream_version,event_type,schema_version,"
        "occurred_at,recorded_at,actor_user_id,correlation_id,causation_id,idempotency_key,title,"
        "description,payload_json,metadata_json,notes,checksum) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        event_rows,
    )
    connection.executemany(
        "INSERT INTO event_subjects "
        "(event_id,subject_type,subject_id,relationship,display_order) VALUES (?,?,?,?,?)",
        subject_rows,
    )
    connection.commit()
    event_rows.clear()
    subject_rows.clear()


def projection_definitions() -> tuple[ProjectionDefinition, ...]:
    ordinary_name = "__snaketracker_test__.qualification_facts"
    fts_name = "__snaketracker_test__.qualification_fts"
    contracts = ((SYNTHETIC_EVENT_TYPE, 2),)
    return (
        ProjectionDefinition(
            name=ordinary_name,
            schema_version=1,
            handler_version=1,
            consistency_class="asynchronous",
            rebuild_group=GROUP,
            physical_identifier="test_qualification_facts",
            components=("data",),
            supported_contracts=contracts,
            strategy=OrdinaryCounterStrategy(ordinary_name),
        ),
        ProjectionDefinition(
            name=fts_name,
            schema_version=1,
            handler_version=1,
            consistency_class="asynchronous",
            rebuild_group=GROUP,
            physical_identifier="test_qualification_fts",
            components=("content", "fts"),
            supported_contracts=contracts,
            strategy=FTSStrategy(fts_name),
        ),
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    database = args.database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    engine, bootstrap, store = initialize_database(database)
    append_latencies: list[float] = []

    def append_one(index: int) -> tuple[float | None, bool]:
        stream_id = UUID(int=5_000_000 + index)
        event = make_event(
            bootstrap.household_id,
            bootstrap.user_id,
            stream_id,
            1,
            label=category_for(index),
        )
        started = time.perf_counter()
        try:
            store.append(
                StreamKey(bootstrap.household_id, SYNTHETIC_STREAM_TYPE, stream_id),
                expected_version=0,
                events=(event,),
            )
        except Exception as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                return None, True
            raise
        return (time.perf_counter() - started) * 1000, False

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        append_results = list(executor.map(append_one, range(args.append_samples)))
    append_latencies.extend(latency for latency, _busy in append_results if latency is not None)
    busy_failures = sum(1 for _latency, busy in append_results if busy)

    seed = bulk_seed(
        database,
        bootstrap.household_id,
        bootstrap.user_id,
        target_events=args.events,
    )
    dataset_bytes = _size(database)
    long_key = StreamKey(bootstrap.household_id, SYNTHETIC_STREAM_TYPE, UUID(int=10_000))
    replay_samples: list[float] = []
    for _index in range(args.replay_samples):
        started = time.perf_counter()
        assert len(store.load_stream(long_key)) == 10_000
        replay_samples.append((time.perf_counter() - started) * 1000)

    long_events = store.load_stream(long_key)
    snapshot_store = SQLAlchemySnapshotRepository(engine)
    snapshot_boundary = 9_900
    snapshot_store.save(
        AggregateSnapshot.create(
            snapshot_id=uuid4(),
            key=long_key,
            stream_version=snapshot_boundary,
            snapshot_schema_version=1,
            aggregate_implementation_version=1,
            boundary_event_id=long_events[snapshot_boundary - 1].event_id,
            state={"value": snapshot_boundary - 1},
            created_at=datetime.now(UTC),
        )
    )
    aggregate_loader = AggregateLoader(
        event_store=store,
        snapshot_repository=snapshot_store,
        initial_state=lambda: -1,
        restore_snapshot=lambda state: cast(int, state["value"]),
        apply_event=lambda _state, event: cast(SyntheticCounterChangedV2, event.payload).value,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
    )
    snapshot_samples: list[float] = []
    snapshot_replayed_events: list[int] = []
    for _index in range(30):
        started = time.perf_counter()
        loaded = aggregate_loader.load(long_key)
        snapshot_samples.append((time.perf_counter() - started) * 1000)
        snapshot_replayed_events.append(loaded.replayed_event_count)
        assert loaded.used_snapshot
        assert loaded.stream_version == 10_000
        assert loaded.state == 9_999

    registry = ProjectionRegistry(projection_definitions(), allow_reserved_test_namespace=True)
    manager = SQLiteProjectionGenerationManager(engine, registry)
    rebuilds: list[dict[str, object]] = []
    projection_peak_wal = 0
    for cache_state in ("cold", "warm"):
        started = time.perf_counter()
        rebuilt = manager.rebuild(GROUP)
        duration = time.perf_counter() - started
        projection_peak_wal = max(
            projection_peak_wal, _size(database.with_name(database.name + "-wal"))
        )
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        rebuilds.append(
            {
                "cache_state": cache_state,
                "duration_seconds": duration,
                "high_water_position": rebuilt.high_water_position,
                "validation": rebuilt.validation,
                "database_bytes": _size(database),
            }
        )
    layout = manager.active_layout(GROUP)
    fts_name = "__snaketracker_test__.qualification_fts"
    fts_table = layout.component(fts_name, "fts")
    fts_latencies: list[float] = []
    with engine.connect() as connection:
        for _index in range(30):
            started = time.perf_counter()
            matches = connection.execute(
                text(f'SELECT count(*) FROM "{fts_table}" WHERE "{fts_table}" MATCH :term'),
                {"term": "feeding"},
            ).scalar_one()
            assert int(matches) > 0
            fts_latencies.append((time.perf_counter() - started) * 1000)
        integrity = str(connection.execute(text("PRAGMA integrity_check")).scalar_one())
        pragmas = {
            name: connection.execute(text(f"PRAGMA {name}")).scalar_one()
            for name in (
                "journal_mode",
                "synchronous",
                "busy_timeout",
                "wal_autocheckpoint",
                "journal_size_limit",
            )
        }
        fts_bytes = int(
            connection.execute(
                text(
                    "SELECT coalesce(sum(pgsize),0) FROM dbstat "
                    "WHERE name LIKE 'test_qualification_fts_%'"
                )
            ).scalar_one()
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    final_bytes = _size(database)
    free_bytes = os.statvfs(database.parent).f_bavail * os.statvfs(database.parent).f_frsize
    with engine.connect() as connection:
        actual_events = int(
            connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one()
        )
    result: dict[str, object] = {
        "schema_version": 1,
        "classification": "M3 development-platform qualification",
        "dataset": {
            "id": DATASET_ID,
            "target_events": args.events,
            "actual_events": actual_events,
            "synthetic_contracts_test_only": True,
            "distribution": {name: percentage for percentage, name in CATEGORIES},
            **seed,
        },
        "environment": {
            "revision": os.environ.get("SNAKETRACKER_QUALIFICATION_REVISION", "unavailable"),
            "image_digest": os.environ.get("SNAKETRACKER_IMAGE_DIGEST", "unavailable"),
            "docker": os.environ.get("SNAKETRACKER_DOCKER_VERSION", "unavailable"),
            "compose": os.environ.get("SNAKETRACKER_COMPOSE_VERSION", "unavailable"),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "sqlite_compile_options": sorted(
                row[0] for row in sqlite3.connect(":memory:").execute("PRAGMA compile_options")
            ),
            "filesystem": os.environ.get("SNAKETRACKER_FILESYSTEM", "container-bind-mount"),
            "cache_states": ["cold", "warm"],
            "concurrency": args.concurrency,
            "encryption": "disabled-local-development",
        },
        "measurements": {
            "append_ms": _summary(append_latencies),
            "busy_failures": busy_failures,
            "busy_failure_percent": busy_failures / args.append_samples * 100,
            "full_10000_event_replay_ms": _summary(replay_samples),
            "snapshot_load_ms": _summary(snapshot_samples),
            "snapshot_boundary_stream_version": snapshot_boundary,
            "snapshot_replayed_event_counts": snapshot_replayed_events,
            "fts_query_ms": _summary(fts_latencies),
            "rebuilds": rebuilds,
            "database_bytes_before_projections": dataset_bytes,
            "database_bytes_final": final_bytes,
            "fts_bytes_all_generations": fts_bytes,
            "peak_observed_projection_wal_bytes": projection_peak_wal,
            "wal_bytes_final": _size(database.with_name(database.name + "-wal")),
            "free_bytes": free_bytes,
            "shadow_headroom_multiple": free_bytes / max(final_bytes, 1),
            "max_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "stream_growth_review_triggered": (
                cast(dict[str, float], _summary(replay_samples))["p95"] > 100
            ),
            "integrity_check": integrity,
            "pragmas": pragmas,
        },
    }
    result["targets"] = evaluate_targets(result)
    engine.dispose()
    return result


def _summary(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0, "min": 0.0, "median": 0.0, "p95": float("inf"), "max": 0.0}
    return {
        "count": len(samples),
        "min": min(samples),
        "median": statistics.median(samples),
        "p95": percentile(samples, 0.95),
        "max": max(samples),
    }


def evaluate_targets(result: dict[str, object]) -> dict[str, bool]:
    measurements = cast(dict[str, object], result["measurements"])
    dataset = cast(dict[str, object], result["dataset"])
    append = cast(dict[str, float], measurements["append_ms"])
    snapshot = cast(dict[str, float], measurements["snapshot_load_ms"])
    fts = cast(dict[str, float], measurements["fts_query_ms"])
    rebuilds = cast(list[dict[str, object]], measurements["rebuilds"])
    return {
        "event_count_matches_target": dataset["actual_events"] == dataset["target_events"],
        "command_p95_at_most_400_ms": append["p95"] <= 400,
        "busy_failures_at_most_0_1_percent": (
            cast(float, measurements["busy_failure_percent"]) <= 0.1
        ),
        "snapshot_load_p95_at_most_50_ms": snapshot["p95"] <= 50,
        "fts_p95_at_most_500_ms": fts["p95"] <= 500,
        "million_event_rebuilds_under_30_minutes": all(
            cast(float, rebuild["duration_seconds"]) <= 1_800 for rebuild in rebuilds
        ),
        "memory_at_most_512_mib": cast(float, measurements["max_rss_mib"]) <= 512,
        "shadow_headroom_at_least_2x": cast(float, measurements["shadow_headroom_multiple"]) >= 2,
        "integrity_check_ok": measurements["integrity_check"] == "ok",
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--events", type=int, default=1_000_000)
    parser.add_argument("--append-samples", type=int, default=100)
    parser.add_argument("--replay-samples", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "results.json"
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    results_path.write_text(rendered, encoding="utf-8")
    checksum = hashlib.sha256(rendered.encode()).hexdigest()
    (args.output_dir / "results.sha256").write_text(f"{checksum}  results.json\n", encoding="utf-8")
    print(rendered, end="")
    return 0 if all(cast(dict[str, bool], result["targets"]).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
