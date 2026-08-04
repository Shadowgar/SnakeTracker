#!/usr/bin/env python3
"""Run the reproducible Phase 1 platform qualification workload."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.maintenance import checkpoint_wal, quick_check
from snaketracker.infrastructure.database.sqlite_profile import qualify_local_filesystem

ROOT = Path(__file__).parents[2]
MANIFEST_SCHEMA_VERSION = 1
DATASET_ID = "phase1-platform-empty-v1"
REQUIRED_SECTIONS = (
    "hardware",
    "operating_system",
    "storage",
    "runtime",
    "test_configuration",
)
READINESS_TARGET_SECONDS = 15.0
MEMORY_TARGET_MIB = 512.0
IDLE_CPU_TARGET_PERCENT = 5.0


class EnvironmentValidationError(ValueError):
    """Raised when a qualification manifest is incomplete or not a pinned Pi host."""


def canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def run_checked(
    command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def validate_manifest(manifest: dict[str, object]) -> None:
    required = {"schema_version", "classification", "revision", *REQUIRED_SECTIONS}
    missing = sorted(required - manifest.keys())
    if missing:
        raise EnvironmentValidationError(f"missing manifest fields: {', '.join(missing)}")
    for section in REQUIRED_SECTIONS:
        value = manifest[section]
        if not isinstance(value, dict) or not value:
            raise EnvironmentValidationError(f"manifest section {section} must be populated")
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise EnvironmentValidationError("unsupported manifest schema version")
    if manifest["classification"] == "qualifying-pi5":
        hardware = manifest["hardware"]
        storage = manifest["storage"]
        operating_system = manifest["operating_system"]
        assert isinstance(hardware, dict)
        assert isinstance(storage, dict)
        assert isinstance(operating_system, dict)
        if hardware.get("architecture") != "aarch64":
            raise EnvironmentValidationError("qualifying host architecture must be aarch64")
        if "raspberry pi 5" not in str(hardware.get("board_model", "")).lower():
            raise EnvironmentValidationError("qualifying board must be Raspberry Pi 5")
        if storage.get("filesystem") != "ext4" or storage.get("medium") != "ssd":
            raise EnvironmentValidationError("qualifying storage must be an ext4 SSD")
        if operating_system.get("image_digest") in {None, "", "unavailable"}:
            raise EnvironmentValidationError("qualifying OS image digest is required")


def optional_output(command: list[str], fallback: str = "unavailable") -> str:
    try:
        value = run_checked(command).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return fallback
    return value or fallback


def board_model() -> str:
    model_path = Path("/proc/device-tree/model")
    try:
        return model_path.read_bytes().rstrip(b"\x00").decode("utf-8")
    except OSError:
        return "development-host"


def parse_cpu_model(cpuinfo: str) -> str:
    values: dict[str, str] = {}
    for line in cpuinfo.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values.setdefault(key.strip().lower(), value.strip())
    for key in ("model name", "hardware", "model"):
        if values.get(key):
            return values[key]
    return "unavailable"


def cpu_model() -> str:
    value = parse_cpu_model(Path("/proc/cpuinfo").read_text(encoding="utf-8"))
    if value != "unavailable":
        return value
    return platform.processor() or "unavailable"


def sqlite_compile_options() -> list[str]:
    with sqlite3.connect(":memory:") as connection:
        return sorted(row[0] for row in connection.execute("PRAGMA compile_options"))


def collect_manifest(
    *, classification: str, cache_state: str, data_path: Path
) -> dict[str, object]:
    mount_fields = optional_output(
        ["findmnt", "-n", "-o", "FSTYPE,OPTIONS,SOURCE", "--target", str(data_path)]
    ).split(maxsplit=2)
    filesystem = mount_fields[0] if mount_fields else "unavailable"
    mount_options = mount_fields[1] if len(mount_fields) > 1 else "unavailable"
    mount_source = mount_fields[2] if len(mount_fields) > 2 else "unavailable"
    image_identity = optional_output(
        ["docker", "image", "inspect", "snaketracker:phase1", "--format", "{{.Id}}"]
    )
    capacity_bytes = int(
        optional_output(["df", "--output=size", "-B1", str(data_path)]).splitlines()[-1]
    )
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "classification": classification,
        "revision": optional_output(["git", "rev-parse", "HEAD"]),
        "hardware": {
            "architecture": platform.machine(),
            "board_model": board_model(),
            "firmware": os.environ.get(
                "SNAKETRACKER_PI_FIRMWARE", optional_output(["vcgencmd", "version"])
            ),
            "cpu": cpu_model(),
            "cooling": os.environ.get("SNAKETRACKER_COOLING", "unavailable"),
        },
        "operating_system": {
            "name": platform.platform(),
            "image_digest": os.environ.get("SNAKETRACKER_OS_IMAGE_DIGEST", "unavailable"),
            "kernel": platform.release(),
        },
        "storage": {
            "filesystem": filesystem,
            "mount_options": mount_options,
            "mount_source": mount_source,
            "medium": os.environ.get("SNAKETRACKER_STORAGE_MEDIUM", "unknown"),
            "controller": os.environ.get("SNAKETRACKER_SSD_CONTROLLER", "unknown"),
            "capacity_bytes": capacity_bytes,
        },
        "runtime": {
            "docker": optional_output(["docker", "--version"]),
            "compose": optional_output(["docker", "compose", "version"]),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "sqlite_compile_options": sqlite_compile_options(),
            "image_digest": image_identity,
        },
        "test_configuration": {
            "encryption": os.environ.get(
                "SNAKETRACKER_ENCRYPTION_CONFIGURATION", "disabled-phase1"
            ),
            "cache_state": cache_state,
            "dataset_id": DATASET_ID,
            "concurrency_mix": "one-health-client; one web worker; one inert worker",
        },
    }
    validate_manifest(manifest)
    return manifest


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def parse_memory_mib(raw: str) -> float:
    match = re.fullmatch(r"([0-9.]+)\s*([KMG]?i?B)", raw.strip())
    if match is None:
        raise ValueError(f"unrecognized Docker memory value: {raw}")
    value, unit = match.groups()
    factors = {
        "B": 1 / 1024**2,
        "KB": 1000 / 1024**2,
        "KiB": 1 / 1024,
        "MB": 1000**2 / 1024**2,
        "MiB": 1,
        "GB": 1000**3 / 1024**2,
        "GiB": 1024,
    }
    return float(value) * factors[unit]


def sqlite_benchmark(database: Path) -> dict[str, object]:
    started = time.perf_counter()
    engine = create_sqlite_engine(database, require_local_storage=True)
    open_ms = (time.perf_counter() - started) * 1000
    commit_samples: list[float] = []
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE qualification_writes (id INTEGER PRIMARY KEY)"))
        for number in range(200):
            started = time.perf_counter()
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO qualification_writes (id) VALUES (:number)"),
                    {"number": number},
                )
            commit_samples.append((time.perf_counter() - started) * 1000)
        with engine.connect() as connection:
            pragmas = {
                "journal_mode": connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(),
                "synchronous": connection.exec_driver_sql("PRAGMA synchronous").scalar_one(),
                "busy_timeout_ms": connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
                "wal_autocheckpoint_pages": connection.exec_driver_sql(
                    "PRAGMA wal_autocheckpoint"
                ).scalar_one(),
                "journal_size_limit_bytes": connection.exec_driver_sql(
                    "PRAGMA journal_size_limit"
                ).scalar_one(),
                "auto_vacuum": connection.exec_driver_sql("PRAGMA auto_vacuum").scalar_one(),
            }
        checkpoint_started = time.perf_counter()
        checkpoint = checkpoint_wal(engine)
        checkpoint_ms = (time.perf_counter() - checkpoint_started) * 1000
        integrity = quick_check(engine)
    finally:
        engine.dispose()
    return {
        "open_ms": round(open_ms, 3),
        "commit_samples": len(commit_samples),
        "commit_p50_ms": round(percentile(commit_samples, 0.50), 3),
        "commit_p95_ms": round(percentile(commit_samples, 0.95), 3),
        "commit_max_ms": round(max(commit_samples), 3),
        "checkpoint_ms": round(checkpoint_ms, 3),
        "checkpoint_result": checkpoint,
        "integrity": integrity,
        "pragmas": pragmas,
    }


def wait_for_readiness(
    url: str, timeout_seconds: float = 30.0, *, started_at: float | None = None
) -> float:
    poll_started = time.perf_counter()
    measurement_started = poll_started if started_at is None else started_at
    while time.perf_counter() - poll_started < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return time.perf_counter() - measurement_started
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"readiness did not succeed within {timeout_seconds:.0f} seconds")


def health_latency(url: str, samples: int = 30) -> dict[str, float | int]:
    durations: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"health request returned {response.status}")
        durations.append((time.perf_counter() - started) * 1000)
    return {
        "samples": samples,
        "p50_ms": round(percentile(durations, 0.50), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "max_ms": round(max(durations), 3),
    }


def container_resources(project: str) -> dict[str, object]:
    container_ids = run_checked(
        ["docker", "compose", "-p", project, "ps", "-q", "web", "worker", "nginx"]
    ).stdout.split()
    output = run_checked(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *container_ids]
    ).stdout
    rows = [json.loads(line) for line in output.splitlines() if line]
    memory_mib = sum(parse_memory_mib(row["MemUsage"].split("/")[0].strip()) for row in rows)
    cpu_percent = sum(float(row["CPUPerc"].rstrip("%")) for row in rows)
    return {
        "containers": len(rows),
        "total_memory_mib": round(memory_mib, 3),
        "total_idle_cpu_percent": round(cpu_percent, 3),
        "raw": rows,
    }


def write_summary(path: Path, manifest: dict[str, object], results: dict[str, object]) -> None:
    targets = results["targets"]
    resources = results["resources"]
    storage = results["storage_qualification"]
    assert isinstance(targets, dict)
    assert isinstance(resources, dict)
    assert isinstance(storage, dict)
    lines = [
        "# Phase 1 qualification summary",
        "",
        f"- Classification: `{manifest['classification']}`",
        f"- Revision: `{manifest['revision']}`",
        f"- Readiness: `{results['readiness_seconds']} s` (target <= {READINESS_TARGET_SECONDS} s)",
        (
            f"- Application memory: `{resources['total_memory_mib']} MiB` "
            f"(target <= {MEMORY_TARGET_MIB} MiB)"
        ),
        (
            f"- Idle CPU: `{resources['total_idle_cpu_percent']}%` "
            f"(target <= {IDLE_CPU_TARGET_PERCENT}% of one core)"
        ),
        f"- Storage qualification: `{storage['status']}`",
        f"- Overall target result: `{'PASS' if all(targets.values()) else 'FAIL'}`",
        "",
        "This result is qualifying only when the manifest classification is `qualifying-pi5`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_qualification(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    project = f"snaketracker-phase1-q-{os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="snaketracker-phase1-") as temporary:
        temporary_path = Path(temporary)
        data_path = temporary_path / "data"
        data_path.mkdir(mode=0o700)
        secret_path = temporary_path / "runtime_secret"
        secret_path.write_text(secrets.token_hex(32), encoding="utf-8")
        secret_path.chmod(0o600)
        port = available_port()
        compose_environment = os.environ.copy()
        compose_environment.update(
            {
                "SNAKETRACKER_DATA_DIR": str(data_path),
                "SNAKETRACKER_RUNTIME_SECRET_FILE": str(secret_path),
                "SNAKETRACKER_HTTP_PORT": str(port),
                "SNAKETRACKER_UID": str(os.getuid()),
            }
        )
        compose = ["docker", "compose", "-p", project]
        manifest = collect_manifest(
            classification=args.classification,
            cache_state=args.cache_state,
            data_path=data_path,
        )
        (output_dir / "environment-manifest.json").write_text(
            canonical_json(manifest), encoding="utf-8"
        )
        started = time.perf_counter()
        try:
            run_checked([*compose, "up", "-d", "--no-build"], env=compose_environment)
            readiness_seconds = wait_for_readiness(
                f"http://127.0.0.1:{port}/health/ready", started_at=started
            )
            time.sleep(args.idle_settle_seconds)
            resources = container_resources(project)
            latency = health_latency(f"http://127.0.0.1:{port}/health/live")
            logs = run_checked([*compose, "logs", "--no-color"], env=compose_environment).stdout
            (output_dir / "compose.log").write_text(logs, encoding="utf-8")
            storage = qualify_local_filesystem(data_path)
            storage_result: dict[str, object] = {
                "status": "supported",
                "filesystem": storage.filesystem,
                "mount_point": str(storage.mount_point),
            }
            sqlite_results = sqlite_benchmark(data_path / "sqlite-benchmark.sqlite3")
        finally:
            shutdown_started = time.perf_counter()
            run_checked([*compose, "down", "--remove-orphans"], env=compose_environment)
            shutdown_seconds = time.perf_counter() - shutdown_started
        results: dict[str, object] = {
            "schema_version": 1,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "readiness_seconds": round(readiness_seconds, 3),
            "shutdown_seconds": round(shutdown_seconds, 3),
            "resources": resources,
            "health_latency": latency,
            "storage_qualification": storage_result,
            "sqlite": sqlite_results,
            "image_size_bytes": int(
                optional_output(
                    [
                        "docker",
                        "image",
                        "inspect",
                        "snaketracker:phase1",
                        "--format",
                        "{{.Size}}",
                    ]
                )
            ),
            "targets": {
                "readiness_at_most_15_seconds": readiness_seconds <= READINESS_TARGET_SECONDS,
                "memory_at_most_512_mib": resources["total_memory_mib"] <= MEMORY_TARGET_MIB,
                "idle_cpu_at_most_5_percent": (
                    resources["total_idle_cpu_percent"] <= IDLE_CPU_TARGET_PERCENT
                ),
                "supported_local_filesystem": storage_result["status"] == "supported",
            },
        }
        (output_dir / "results.json").write_text(canonical_json(results), encoding="utf-8")
        write_summary(output_dir / "summary.md", manifest, results)
    targets = results["targets"]
    assert isinstance(targets, dict)
    if args.classification == "qualifying-pi5" and not all(targets.values()):
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--classification",
        choices=("non-qualifying-development", "qualifying-pi5"),
        default="non-qualifying-development",
    )
    parser.add_argument("--cache-state", choices=("cold", "warm"), default="warm")
    parser.add_argument("--idle-settle-seconds", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    try:
        return run_qualification(parse_args())
    except EnvironmentValidationError as error:
        print(f"qualification environment rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
