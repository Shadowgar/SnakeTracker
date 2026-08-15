#!/usr/bin/env python3
"""Generate the versioned M6 representative dataset specification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DATASET_ID = "snaketracker-reference-v1-m6-product-experience"


def build_dataset(*, animal_count: int = 100) -> dict[str, Any]:
    if animal_count < 5:
        raise ValueError("The M6 dataset requires at least five animals.")
    animals = []
    for index in range(animal_count):
        animal_type = "snake" if index % 5 < 3 else "spider"
        animals.append(
            {
                "fixture_id": f"animal-{index + 1:04d}",
                "animal_type": animal_type,
                "capability_profile": f"{animal_type}.v1",
                "name": f"{animal_type.title()} {index + 1:04d}",
                "species": "Python regius" if animal_type == "snake" else "Tliltocatl albopilosus",
                "notes": f"M6 deterministic search note {index % 10}",
            }
        )
    return {
        "schema_version": 1,
        "dataset_id": DATASET_ID,
        "timezone": "America/New_York",
        "animals": animals,
        "history_policy": {
            "accepted_feeding_intervals_days": [10, 11, 9, 10, 10, 12, 10, 9],
            "snake_shed_intervals_days": [45, 48, 46, 47, 45, 46],
            "spider_molt_intervals_days": [60, 60, 60, 60, 60, 60],
            "correction_void_reinstatement_cases": 3,
        },
        "household_isolation_fixtures": 2,
        "financial_capability_fixtures": 2,
        "cache_states": ["cold", "warm"],
        "concurrency_mix": {"readers": 10, "projection_workers": 1},
        "production_husbandry_guidance": "unavailable-pending-owner-source-approval",
    }


def canonical_bytes(dataset: dict[str, Any]) -> bytes:
    return (json.dumps(dataset, indent=2, sort_keys=True) + "\n").encode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--animals", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered = canonical_bytes(build_dataset(animal_count=args.animals))
    (args.output_dir / "dataset.json").write_bytes(rendered)
    checksum = hashlib.sha256(rendered).hexdigest()
    (args.output_dir / "dataset.sha256").write_text(f"{checksum}  dataset.json\n", encoding="utf-8")
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
