from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
MODULE_PATH = ROOT / "scripts/benchmarks/phase1_qualification.py"
SPEC = importlib.util.spec_from_file_location("phase1_qualification", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
qualification = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qualification
SPEC.loader.exec_module(qualification)

EnvironmentValidationError = qualification.EnvironmentValidationError
canonical_json = qualification.canonical_json
run_checked = qualification.run_checked
validate_manifest = qualification.validate_manifest
parse_memory_mib = qualification.parse_memory_mib
parse_cpu_model = qualification.parse_cpu_model


def complete_manifest() -> dict[str, object]:
    return {
        "schema_version": 2,
        "classification": "non-qualifying-development",
        "revision": "abc123",
        "hardware": {
            "architecture": "x86_64",
            "board_model": "development-host",
            "firmware": "not-applicable",
            "cpu": "test-cpu",
            "cooling": "development-host",
            "cpu_governor": "performance",
            "temperature": "unavailable",
            "throttle_status": "unavailable",
        },
        "operating_system": {
            "name": "Test OS",
            "image_digest": "unavailable",
            "kernel": "test-kernel",
        },
        "storage": {
            "filesystem": "overlay",
            "mount_options": "rw",
            "mount_source": "overlay",
            "medium": "unknown",
            "controller": "unknown",
            "capacity_bytes": 1,
            "device_path": "/dev/test",
            "rotational": True,
            "ssd_verified": False,
            "transport": "unknown",
        },
        "runtime": {
            "docker": "29",
            "compose": "2",
            "python": "3.13.14",
            "sqlite": "3",
            "sqlite_compile_options": [],
            "image_digest": "sha256:test",
        },
        "test_configuration": {
            "encryption": "disabled-phase1",
            "cache_state": "warm",
            "cache_preparation": "unspecified",
            "boot_id": "test-boot",
            "uptime_seconds": 100,
            "dataset_id": "phase1-platform-empty-v1",
            "concurrency_mix": "one-health-client",
        },
    }


def test_manifest_rejects_missing_required_field() -> None:
    manifest = complete_manifest()
    del manifest["storage"]

    with pytest.raises(EnvironmentValidationError, match="storage"):
        validate_manifest(manifest)


def test_manifest_rejects_missing_nested_field() -> None:
    manifest = complete_manifest()
    hardware = manifest["hardware"]
    assert isinstance(hardware, dict)
    del hardware["firmware"]

    with pytest.raises(EnvironmentValidationError, match=r"hardware\.firmware"):
        validate_manifest(manifest)


def test_qualifying_manifest_rejects_non_pi_environment() -> None:
    manifest = complete_manifest()
    manifest["classification"] = "qualifying-pi5"

    with pytest.raises(EnvironmentValidationError, match="aarch64"):
        validate_manifest(manifest)


def test_canonical_json_is_deterministic() -> None:
    first = canonical_json({"z": 1, "a": {"y": 2, "b": 3}})
    second = canonical_json(json.loads(first))

    assert first == second
    assert first.endswith("\n")


def test_command_failure_propagates(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as raised:
        run_checked(["sh", "-c", "exit 23"], cwd=tmp_path)

    assert raised.value.returncode == 23


def test_docker_memory_value_parses_compact_unit() -> None:
    assert parse_memory_mib("12.5MiB") == 12.5
    assert parse_memory_mib("1GiB") == 1024


def test_readiness_measurement_can_include_launcher_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    clock = iter((2.0, 2.0, 5.0))
    monkeypatch.setattr(qualification.time, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(
        qualification.urllib.request, "urlopen", lambda *_args, **_kwargs: Response()
    )

    elapsed = qualification.wait_for_readiness("http://test", started_at=1.0)

    assert elapsed == 4.0


def test_cpu_model_prefers_descriptive_model_name() -> None:
    cpuinfo = "processor : 0\nmodel : 141\nmodel name : Example CPU 9000\n"

    assert parse_cpu_model(cpuinfo) == "Example CPU 9000"


def test_sqlite_contract_targets_fail_when_durability_drifts() -> None:
    results = {
        "integrity": "ok",
        "fts5": True,
        "checkpoint_result": (0, 1, 1),
        "pragmas": {
            "auto_vacuum": 2,
            "busy_timeout_ms": 5_000,
            "journal_mode": "wal",
            "journal_size_limit_bytes": 256 * 1024 * 1024,
            "synchronous": 1,
            "wal_autocheckpoint_pages": 1_000,
        },
    }

    targets = qualification.sqlite_contract_targets(results)

    assert targets["sqlite_full_durability"] is False
    assert all(value for key, value in targets.items() if key != "sqlite_full_durability")


def test_candidate_root_rejects_broad_or_missing_paths(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentValidationError):
        qualification.validate_candidate_root(Path("/"))
    with pytest.raises(EnvironmentValidationError):
        qualification.validate_candidate_root(tmp_path / "missing")

    assert qualification.validate_candidate_root(tmp_path) == tmp_path.resolve()


def test_cli_requires_an_explicit_candidate_data_root(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        qualification.parse_args(["--output-dir", str(tmp_path / "evidence")])

    args = qualification.parse_args(
        [
            "--output-dir",
            str(tmp_path / "evidence"),
            "--candidate-data-root",
            str(tmp_path),
        ]
    )

    assert args.candidate_data_root == tmp_path


def test_qualifying_cache_state_requires_documented_preparation() -> None:
    with pytest.raises(EnvironmentValidationError, match="cache preparation"):
        qualification.validate_cache_preparation("qualifying-pi5", "cold", "unspecified")

    assert (
        qualification.validate_cache_preparation(
            "qualifying-pi5", "cold", "sync; drop_caches=3; image preloaded"
        )
        == "sync; drop_caches=3; image preloaded"
    )


def test_persistence_check_requires_same_schema_revision_and_database() -> None:
    assert qualification.persistence_targets(
        database_exists=True,
        schema_before="0001_phase1_baseline",
        schema_after="0001_phase1_baseline",
    ) == {
        "database_exists_after_restart": True,
        "schema_revision_preserved_after_restart": True,
    }

    assert qualification.persistence_targets(
        database_exists=False,
        schema_before="0001_phase1_baseline",
        schema_after=None,
    ) == {
        "database_exists_after_restart": False,
        "schema_revision_preserved_after_restart": False,
    }
