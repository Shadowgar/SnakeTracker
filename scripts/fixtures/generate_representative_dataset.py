#!/usr/bin/env python3
"""Generate the versioned M6 representative dataset specification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DATASET_ID = "care-keeper-reference-v2-four-group-capabilities"
ANIMAL_GROUPS = ("snake",) * 4 + ("spider",) * 3 + ("lizard",) * 3 + ("scorpion",) * 3
SPECIES = {
    "snake": "Python regius",
    "spider": "Tliltocatl albopilosus",
    "lizard": "Pogona vitticeps",
    "scorpion": "Heterometrus spinifer",
}


def build_dataset(*, animal_count: int = 100) -> dict[str, Any]:
    if animal_count < 8:
        raise ValueError("The four-group dataset requires at least eight animals.")
    animals = []
    for index in range(animal_count):
        animal_type = ANIMAL_GROUPS[index % len(ANIMAL_GROUPS)]
        animals.append(
            {
                "fixture_id": f"animal-{index + 1:04d}",
                "animal_type": animal_type,
                "capability_profile": f"{animal_type}.v1",
                "name": f"{animal_type.title()} {index + 1:04d}",
                "species": SPECIES[animal_type],
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
            "molt_intervals_days": {
                "spider": [60, 60, 60, 60, 60, 60],
                "scorpion": [70, 73, 71, 74, 72, 71],
            },
            "lizard_measurement_kinds": ["weight", "length"],
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
