from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "scripts/fixtures/seed_m6_owner_review.py"
SPEC = importlib.util.spec_from_file_location("seed_m6_owner_review", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
seeder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seeder
SPEC.loader.exec_module(seeder)

seed_demo = seeder.seed_demo


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def test_owner_review_demo_is_isolated_populated_and_prediction_ready(tmp_path: Path) -> None:
    normal_database = tmp_path / "normal" / "snaketracker.sqlite3"
    normal_database.parent.mkdir()
    normal_database.write_bytes(b"keeper-data-must-not-change")
    demo_dir = tmp_path / "m6-owner-review-demo"

    result = seed_demo(demo_dir, as_of=date(2026, 8, 15))

    assert normal_database.read_bytes() == b"keeper-data-must-not-change"
    assert result.animal_count == 5
    assert result.scenario_version == "m6-owner-review.v1"
    assert result.snake_count == 2
    assert result.spider_count == 3
    assert result.profile_photo_count == 5
    assert result.prediction_ready == ("Ember", "Juniper")
    assert result.insufficient_history_animal == "Pip"
    assert result.event_count >= 80
    with sqlite3.connect(demo_dir / "snaketracker.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM animal_current").fetchone() == (5,)
        assert connection.execute("SELECT count(*) FROM attachment_versions").fetchone() == (5,)
        assert connection.execute("SELECT count(*) FROM reminder_rule_current").fetchone()[0] >= 3
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    photos = tuple((demo_dir / "attachments" / "versions").glob("*.png"))
    assert len(photos) == 5
    assert len({hashlib.sha256(photo.read_bytes()).digest() for photo in photos}) == 5
    assert {image_size(photo) for photo in photos} == {(640, 480)}


def test_owner_review_demo_refuses_to_overwrite_an_existing_database(tmp_path: Path) -> None:
    demo_dir = tmp_path / "m6-owner-review-demo"
    seed_demo(demo_dir, as_of=date(2026, 8, 15))

    try:
        seed_demo(demo_dir, as_of=date(2026, 8, 15))
    except FileExistsError as error:
        assert "--replace" in str(error)
    else:
        raise AssertionError("Demo seeding must not overwrite an existing database by default.")


def test_owner_review_demo_refuses_a_nondemo_target(tmp_path: Path) -> None:
    target = tmp_path / "normal-keeper-data"

    try:
        seed_demo(target, as_of=date(2026, 8, 15), replace=True)
    except ValueError as error:
        assert "must contain 'demo'" in str(error)
    else:
        raise AssertionError("Demo seeding must refuse a target not explicitly named as demo data.")
