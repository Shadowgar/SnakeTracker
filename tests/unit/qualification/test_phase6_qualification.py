from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
MODULE_PATH = ROOT / "scripts/fixtures/generate_representative_dataset.py"
SPEC = importlib.util.spec_from_file_location("generate_representative_dataset", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)

build_dataset = generator.build_dataset
canonical_bytes = generator.canonical_bytes


def test_m6_dataset_is_deterministic_mixed_and_contains_no_guidance() -> None:
    first = build_dataset(animal_count=10)
    second = build_dataset(animal_count=10)

    assert (
        hashlib.sha256(canonical_bytes(first)).digest()
        == hashlib.sha256(canonical_bytes(second)).digest()
    )
    assert {animal["animal_type"] for animal in first["animals"]} == {"snake", "spider"}
    assert first["production_husbandry_guidance"].startswith("unavailable")


def test_m6_dataset_rejects_nonrepresentative_size() -> None:
    with pytest.raises(ValueError, match="at least five"):
        build_dataset(animal_count=4)


def test_phase6_qualification_runner_has_reproducible_cli() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.benchmarks.phase6_qualification", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--database" in completed.stdout
    assert "--output-dir" in completed.stdout
