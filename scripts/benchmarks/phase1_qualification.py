#!/usr/bin/env python3
"""Run the reproducible Phase 1 platform qualification workload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shlex
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.maintenance import checkpoint_wal, quick_check
from snaketracker.infrastructure.database.sqlite_profile import qualify_local_filesystem

ROOT = Path(__file__).parents[2]
MANIFEST_SCHEMA_VERSION = 2
DATASET_ID = "phase1-platform-empty-v1"
REQUIRED_SECTIONS = (
    "hardware",
    "operating_system",
    "storage",
    "runtime",
    "test_configuration",
)
REQUIRED_SECTION_FIELDS = {
    "hardware": {
        "architecture",
        "board_model",
        "cooling",
        "cpu",
        "cpu_governor",
        "firmware",
        "temperature",
        "throttle_status",
    },
    "operating_system": {"image_digest", "kernel", "name"},
    "storage": {
        "capacity_bytes",
        "controller",
        "device_path",
        "filesystem",
        "medium",
        "mount_options",
        "mount_source",
        "rotational",
        "ssd_verified",
        "transport",
    },
    "runtime": {
        "compose",
        "docker",
        "image_digest",
        "python",
        "sqlite",
        "sqlite_compile_options",
    },
    "test_configuration": {
        "boot_id",
        "cache_preparation",
        "cache_state",
        "concurrency_mix",
        "dataset_id",
        "encryption",
        "uptime_seconds",
    },
}
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
        missing_fields = sorted(REQUIRED_SECTION_FIELDS[section] - value.keys())
        if missing_fields:
            names = ", ".join(f"{section}.{field}" for field in missing_fields)
            raise EnvironmentValidationError(f"missing manifest fields: {names}")
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
        if storage.get("filesystem") != "ext4" or storage.get("ssd_verified") is not True:
            raise EnvironmentValidationError("qualifying storage must be an ext4 SSD")
        if not str(operating_system.get("image_digest", "")).startswith("sha256:"):
            raise EnvironmentValidationError("qualifying OS image digest is required")
        for field in ("firmware", "cooling", "cpu_governor"):
            if hardware.get(field) in {None, "", "unavailable"}:
                raise EnvironmentValidationError(f"qualifying hardware.{field} is required")
        if hardware.get("throttle_status") != "throttled=0x0":
            raise EnvironmentValidationError("qualifying host must report no throttling")


def validate_candidate_root(candidate: Path) -> Path:
    resolved = candidate.resolve(strict=False)
    if resolved in {Path("/"), Path.home().resolve()}:
        raise EnvironmentValidationError("candidate data directory is too broad")
    if not resolved.is_dir():
        raise EnvironmentValidationError("candidate data directory must already exist")
    if not os.access(resolved, os.W_OK | os.X_OK):
        raise EnvironmentValidationError("candidate data directory must be writable")
    return resolved


def validate_cache_preparation(
    classification: str, cache_state: str, cache_preparation: str
) -> str:
    preparation = cache_preparation.strip()
    if classification == "qualifying-pi5" and preparation in {"", "unspecified"}:
        raise EnvironmentValidationError(
            f"qualifying {cache_state} cache preparation must be documented"
        )
    return preparation or "unspecified"


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


def file_value(path: Path, fallback: str = "unavailable") -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or fallback
    except OSError:
        return fallback


def parse_block_device_fields(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in shlex.split(raw):
        key, separator, value = token.partition("=")
        if separator:
            fields[key] = value
    return fields


def measured_block_storage(mount_source: str) -> dict[str, object]:
    source = mount_source.split("[", 1)[0]
    if not source.startswith("/dev/"):
        return {
            "capacity_bytes": 0,
            "controller": "unavailable",
            "device_path": source,
            "medium": "unverified",
            "rotational": None,
            "ssd_verified": False,
            "transport": "unavailable",
        }
    parent = optional_output(["lsblk", "-ndo", "PKNAME", source], fallback="")
    device = f"/dev/{parent}" if parent else source
    fields = parse_block_device_fields(
        optional_output(["lsblk", "-bdPno", "TYPE,ROTA,TRAN,SIZE,MODEL", device])
    )
    required_fields = {"TYPE", "ROTA", "TRAN", "SIZE", "MODEL"}
    if not required_fields.issubset(fields) or not fields["SIZE"].isdigit():
        return {
            "capacity_bytes": 0,
            "controller": "unavailable",
            "device_path": device,
            "medium": "unverified",
            "rotational": None,
            "ssd_verified": False,
            "transport": "unavailable",
        }
    device_type = fields["TYPE"]
    rotational_raw = fields["ROTA"]
    transport = fields["TRAN"]
    capacity_raw = fields["SIZE"]
    model = fields["MODEL"] or "unavailable"
    rotational = rotational_raw == "1"
    accepted_transport = transport.lower() in {"ata", "nvme", "sata", "usb"}
    ssd_verified = device_type == "disk" and not rotational and accepted_transport
    return {
        "capacity_bytes": int(capacity_raw),
        "controller": model,
        "device_path": device,
        "medium": "ssd" if ssd_verified else "unverified",
        "rotational": rotational,
        "ssd_verified": ssd_verified,
        "transport": transport,
    }


def collect_manifest(
    *, classification: str, cache_state: str, cache_preparation: str, data_path: Path
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
    block_storage = measured_block_storage(mount_source)
    uptime_raw = file_value(Path("/proc/uptime"), "0").split()[0]
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
            "cpu_governor": file_value(
                Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
            ),
            "temperature": optional_output(["vcgencmd", "measure_temp"]),
            "throttle_status": optional_output(["vcgencmd", "get_throttled"]),
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
            **block_storage,
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
            "cache_preparation": cache_preparation,
            "boot_id": file_value(Path("/proc/sys/kernel/random/boot_id")),
            "uptime_seconds": round(float(uptime_raw), 3),
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


def sqlite_contract_targets(results: dict[str, object]) -> dict[str, bool]:
    pragmas = results["pragmas"]
    checkpoint = results["checkpoint_result"]
    assert isinstance(pragmas, dict)
    assert isinstance(checkpoint, (list, tuple))
    return {
        "sqlite_wal": pragmas.get("journal_mode") == "wal",
        "sqlite_full_durability": pragmas.get("synchronous") == 2,
        "sqlite_busy_timeout_5000_ms": pragmas.get("busy_timeout_ms") == 5_000,
        "sqlite_wal_autocheckpoint_1000_pages": (pragmas.get("wal_autocheckpoint_pages") == 1_000),
        "sqlite_journal_limit_256_mib": (
            pragmas.get("journal_size_limit_bytes") == 256 * 1024 * 1024
        ),
        "sqlite_incremental_auto_vacuum": pragmas.get("auto_vacuum") == 2,
        "sqlite_fts5_available": results.get("fts5") is True,
        "sqlite_quick_check_ok": results.get("integrity") == "ok",
        "sqlite_checkpoint_not_busy": len(checkpoint) == 3 and checkpoint[0] == 0,
    }


def schema_revision(database: Path) -> str | None:
    if not database.is_file():
        return None
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def persistence_targets(
    *, database_exists: bool, schema_before: str | None, schema_after: str | None
) -> dict[str, bool]:
    return {
        "database_exists_after_restart": database_exists,
        "schema_revision_preserved_after_restart": (
            schema_before is not None and schema_before == schema_after
        ),
    }


def sqlite_benchmark(database: Path) -> dict[str, object]:
    started = time.perf_counter()
    engine = create_sqlite_engine(database, require_local_storage=True)
    open_ms = (time.perf_counter() - started) * 1000
    commit_samples: list[float] = []
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE qualification_writes (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE VIRTUAL TABLE qualification_fts USING fts5(value)"))
        fts5 = True
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
        "fts5": fts5,
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


def container_resources(
    project: str,
    *,
    env: dict[str, str],
    samples: int,
    sample_interval_seconds: float,
) -> dict[str, object]:
    container_ids = run_checked(
        ["docker", "compose", "-p", project, "ps", "-q", "web", "worker", "nginx"],
        env=env,
    ).stdout.split()
    if len(container_ids) != 3:
        raise RuntimeError(f"expected three running containers, found {len(container_ids)}")
    measurements: list[dict[str, object]] = []
    memory_samples: list[float] = []
    cpu_samples: list[float] = []
    for sample_number in range(samples):
        output = run_checked(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *container_ids]
        ).stdout
        rows: list[dict[str, Any]] = [json.loads(line) for line in output.splitlines() if line]
        memory_mib = sum(
            parse_memory_mib(str(row["MemUsage"]).split("/")[0].strip()) for row in rows
        )
        cpu_percent = sum(float(str(row["CPUPerc"]).rstrip("%")) for row in rows)
        memory_samples.append(memory_mib)
        cpu_samples.append(cpu_percent)
        measurements.append(
            {
                "cpu_percent": round(cpu_percent, 3),
                "memory_mib": round(memory_mib, 3),
                "raw": rows,
            }
        )
        if sample_number + 1 < samples:
            time.sleep(sample_interval_seconds)
    return {
        "containers": len(container_ids),
        "samples": samples,
        "sample_interval_seconds": sample_interval_seconds,
        "peak_memory_mib": round(max(memory_samples), 3),
        "memory_variance": round(statistics.pvariance(memory_samples), 6),
        "idle_cpu_p95_percent": round(percentile(cpu_samples, 0.95), 3),
        "idle_cpu_variance": round(statistics.pvariance(cpu_samples), 6),
        "raw": measurements,
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
            f"- Peak application memory: `{resources['peak_memory_mib']} MiB` "
            f"(target <= {MEMORY_TARGET_MIB} MiB)"
        ),
        (
            f"- Idle CPU p95: `{resources['idle_cpu_p95_percent']}%` "
            f"(target <= {IDLE_CPU_TARGET_PERCENT}% of one core)"
        ),
        f"- Restart readiness: `{results['restart_readiness_seconds']} s`",
        f"- Storage qualification: `{storage['status']}`",
        f"- Overall target result: `{'PASS' if all(targets.values()) else 'FAIL'}`",
        "",
        "This result is qualifying only when the manifest classification is `qualifying-pi5`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_qualification(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_root = validate_candidate_root(args.candidate_data_root)
    cache_preparation = validate_cache_preparation(
        args.classification, args.cache_state, args.cache_preparation
    )
    project = f"snaketracker-phase1-q-{os.getpid()}"
    with tempfile.TemporaryDirectory(
        prefix="snaketracker-phase1-", dir=candidate_root
    ) as temporary:
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
            cache_preparation=cache_preparation,
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
            resources = container_resources(
                project,
                env=compose_environment,
                samples=args.resource_samples,
                sample_interval_seconds=args.resource_sample_interval_seconds,
            )
            peak_memory_mib = resources["peak_memory_mib"]
            idle_cpu_p95_percent = resources["idle_cpu_p95_percent"]
            assert isinstance(peak_memory_mib, (int, float))
            assert isinstance(idle_cpu_p95_percent, (int, float))
            latency = health_latency(f"http://127.0.0.1:{port}/health/live")
            storage = qualify_local_filesystem(data_path)
            storage_result: dict[str, object] = {
                "status": "supported",
                "filesystem": storage.filesystem,
                "mount_point": str(storage.mount_point),
            }
            database = data_path / "snaketracker.sqlite3"
            schema_before_restart = schema_revision(database)
            restart_started = time.perf_counter()
            run_checked([*compose, "restart", "web", "worker", "nginx"], env=compose_environment)
            restart_readiness_seconds = wait_for_readiness(
                f"http://127.0.0.1:{port}/health/ready", started_at=restart_started
            )
            schema_after_restart = schema_revision(database)
            persistence = persistence_targets(
                database_exists=database.is_file(),
                schema_before=schema_before_restart,
                schema_after=schema_after_restart,
            )
            logs = run_checked([*compose, "logs", "--no-color"], env=compose_environment).stdout
            (output_dir / "compose.log").write_text(logs, encoding="utf-8")
            sqlite_results = sqlite_benchmark(data_path / "sqlite-benchmark.sqlite3")
        finally:
            shutdown_started = time.perf_counter()
            run_checked([*compose, "down", "--remove-orphans"], env=compose_environment)
            shutdown_seconds = time.perf_counter() - shutdown_started
        results: dict[str, object] = {
            "schema_version": 2,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "readiness_seconds": round(readiness_seconds, 3),
            "restart_readiness_seconds": round(restart_readiness_seconds, 3),
            "shutdown_seconds": round(shutdown_seconds, 3),
            "resources": resources,
            "health_latency": latency,
            "storage_qualification": storage_result,
            "sqlite": sqlite_results,
            "persistence": {
                "schema_before_restart": schema_before_restart,
                "schema_after_restart": schema_after_restart,
                **persistence,
            },
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
                "restart_readiness_at_most_15_seconds": (
                    restart_readiness_seconds <= READINESS_TARGET_SECONDS
                ),
                "memory_at_most_512_mib": peak_memory_mib <= MEMORY_TARGET_MIB,
                "idle_cpu_at_most_5_percent": (idle_cpu_p95_percent <= IDLE_CPU_TARGET_PERCENT),
                "supported_local_filesystem": storage_result["status"] == "supported",
                **persistence,
                **sqlite_contract_targets(sqlite_results),
            },
        }
        (output_dir / "results.json").write_text(canonical_json(results), encoding="utf-8")
        write_summary(output_dir / "summary.md", manifest, results)
        hashed_artifacts = (
            "environment-manifest.json",
            "results.json",
            "compose.log",
            "summary.md",
        )
        hashes = {name: file_sha256(output_dir / name) for name in hashed_artifacts}
        (output_dir / "artifact-hashes.json").write_text(
            canonical_json({"algorithm": "sha256", "files": hashes}), encoding="utf-8"
        )
    targets = results["targets"]
    assert isinstance(targets, dict)
    if args.classification == "qualifying-pi5" and not all(targets.values()):
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-data-root", type=Path, required=True)
    parser.add_argument(
        "--classification",
        choices=("non-qualifying-development", "qualifying-pi5"),
        default="non-qualifying-development",
    )
    parser.add_argument("--cache-state", choices=("cold", "warm"), default="warm")
    parser.add_argument("--cache-preparation", default="unspecified")
    parser.add_argument("--idle-settle-seconds", type=float, default=5.0)
    parser.add_argument("--resource-samples", type=int, default=12)
    parser.add_argument("--resource-sample-interval-seconds", type=float, default=5.0)
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run_qualification(parse_args())
    except EnvironmentValidationError as error:
        print(f"qualification environment rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
