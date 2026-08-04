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
        "schema_version": 1,
        "classification": "non-qualifying-development",
        "revision": "abc123",
        "hardware": {
            "architecture": "x86_64",
            "board_model": "development-host",
            "firmware": "not-applicable",
            "cpu": "test-cpu",
            "cooling": "development-host",
        },
        "operating_system": {
            "name": "Test OS",
            "image_digest": "unavailable",
            "kernel": "test-kernel",
        },
        "storage": {
            "filesystem": "overlay",
            "mount_options": "rw",
            "medium": "unknown",
            "controller": "unknown",
            "capacity_bytes": 1,
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
            "dataset_id": "phase1-platform-empty-v1",
            "concurrency_mix": "one-health-client",
        },
    }


def test_manifest_rejects_missing_required_field() -> None:
    manifest = complete_manifest()
    del manifest["storage"]

    with pytest.raises(EnvironmentValidationError, match="storage"):
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
