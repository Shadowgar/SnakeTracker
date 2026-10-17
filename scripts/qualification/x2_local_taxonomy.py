"""Reproducible synthetic Pi measurements; all databases are temporary and isolated."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path

from alembic import command
from alembic.config import Config

from snaketracker.application.local_taxonomy import GenerationSource
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

ROOT = Path(__file__).resolve().parents[2]


def measure(rows: int, previous_package: Path | None) -> dict[str, object]:
    if not 10 <= rows <= 10000:
        raise ValueError("Synthetic development measurements accept 10-10000 rows.")
    with tempfile.TemporaryDirectory(prefix="care-keeper-x2-measure-") as temporary:
        database = Path(temporary) / "synthetic.db"
        config = Config(ROOT / "alembic.ini")
        config.set_main_option("script_location", str(ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
        command.upgrade(config, "head")
        engine = create_sqlite_engine(database, require_local_storage=False)
        catalog = LocalTaxonomyCatalog(engine)
        now = datetime.now(UTC)
        facts = [
            ProviderTaxon(
                "fixture",
                str(index),
                "https://example.test/taxa/" + str(index),
                "",
                f"Synthetic species {index:06d}",
                preferred_common_name=f"Fixture name {index:06d}",
                class_name="Amphibia" if index % 2 else "Reference classification",
            )
            for index in range(rows)
        ]
        start, cpu = time.perf_counter(), time.process_time()
        generation = catalog.begin_generation(
            GenerationSource(
                "Synthetic Pi qualification",
                "fixture",
                "https://example.test/archive",
                now,
                now,
                "a" * 64,
                "Synthetic generated facts",
            ),
            imported_at=now,
        )
        for batch in batched(facts, 500, strict=False):
            catalog.stage(generation, batch)
        catalog.validate_generation(generation)
        import_seconds = time.perf_counter() - start
        import_cpu = time.process_time() - cpu
        start = time.perf_counter()
        catalog.promote(generation)
        promotion_seconds = time.perf_counter() - start
        engine.dispose()
        start = time.perf_counter()
        first = catalog.search("Synthetic species")[0]
        first_search_seconds = time.perf_counter() - start
        warm = []
        for _ in range(50):
            start = time.perf_counter()
            assert catalog.search("Fixture name")
            warm.append(time.perf_counter() - start)
        start = time.perf_counter()
        assert catalog.resolve(first.taxon_id).scientific_name == first.scientific_name
        detail_seconds = time.perf_counter() - start
        with engine.connect() as connection:
            sqlite_version = connection.exec_driver_sql("SELECT sqlite_version()").scalar_one()
            pragmas = {
                key: connection.exec_driver_sql("PRAGMA " + key).scalar_one()
                for key in ("journal_mode", "synchronous", "foreign_keys")
            }
            plan = [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "EXPLAIN QUERY PLAN SELECT taxon_id FROM taxonomy_search "
                    "WHERE taxonomy_search MATCH ?",
                    ('"synthetic"*',),
                )
            ]
            sizes = {
                row[0]: row[1]
                for row in connection.exec_driver_sql(
                    "SELECT name,sum(pgsize) FROM dbstat GROUP BY name"
                )
            }
        storage = {path.name: path.stat().st_size for path in Path(temporary).glob("synthetic.db*")}
        engine.dispose()
        rollback_binary: object = "Not requested"
        if previous_package is not None:
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            code = """import json,snaketracker,sys
from pathlib import Path
from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
engine=create_readonly_sqlite_engine(Path(sys.argv[1]))
try:
 report=inspect_startup_compatibility(engine)
 print(json.dumps({"package":snaketracker.__file__,"ready":report.normal_readiness,"reason":report.reason_code}))
finally: engine.dispose()
"""
            result = subprocess.run(
                [sys.executable, "-c", code, str(database)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "PYTHONPATH": str(previous_package.resolve())},
            )
            rollback_binary = json.loads(result.stdout)
            assert previous_package.resolve() in Path(rollback_binary["package"]).parents
            assert rollback_binary["ready"] is False
            assert before == hashlib.sha256(database.read_bytes()).hexdigest()
        model = Path("/proc/device-tree/model")
        return {
            "scope": "synthetic development; no production archive or production acceptance",
            "hardware": model.read_text().strip("\x00") if model.exists() else platform.machine(),
            "load_average": os.getloadavg(),
            "rows": rows,
            "sqlite_version": sqlite_version,
            "import_seconds": import_seconds,
            "import_cpu_seconds": import_cpu,
            "promotion_seconds": promotion_seconds,
            "first_new_connection_search_seconds": first_search_seconds,
            "warm_search_median_seconds": statistics.median(warm),
            "warm_search_p95_seconds": sorted(warm)[47],
            "exact_detail_seconds": detail_seconds,
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "storage_bytes": storage,
            "sqlite_object_bytes": sizes,
            "pragmas": pragmas,
            "search_query_plan": plan,
            "previous_x1_package_on_x2_schema": rollback_binary,
            "cold_disk_cache_measurement": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--previous-package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.rows, args.previous_package)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
