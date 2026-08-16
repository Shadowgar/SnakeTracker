from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from snaketracker.application.household_bootstrap import (
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from tests.integration.test_household_bootstrap import command_for, migrated_engine

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
    data_dir = tmp_path / "promoted-runtime"
    data_dir.mkdir()
    database = data_dir / "snaketracker.sqlite3"
    engine = migrated_engine(database)
    real = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    ).bootstrap(command_for())
    with engine.connect() as connection:
        real_events_before = connection.execute(
            text("SELECT count(*) FROM domain_events WHERE household_id=:household_id"),
            {"household_id": str(real.household_id)},
        ).scalar_one()
    engine.dispose()

    result = seed_demo(data_dir, as_of=date(2026, 8, 15))

    assert result.animal_count == 12
    assert result.enclosure_count == 9
    assert result.scenario_version == "m6-owner-review.v2"
    assert result.snake_count == 6
    assert result.spider_count == 6
    assert result.profile_photo_count == 12
    assert result.prediction_ready == ("Ember", "Juniper", "Nova", "Pearl")
    assert result.insufficient_history_animal == "Pip"
    assert result.event_count >= 300
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM animal_current WHERE household_id=?",
            (result.household_id,),
        ).fetchone() == (12,)
        assert connection.execute(
            "SELECT count(*) FROM attachment_versions WHERE household_id=?",
            (result.household_id,),
        ).fetchone() == (12,)
        assert connection.execute("SELECT count(*) FROM reminder_rule_current").fetchone()[0] >= 3
        assert connection.execute(
            "SELECT count(*) FROM domain_events WHERE household_id=?",
            (str(real.household_id),),
        ).fetchone() == (real_events_before,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    photos = tuple((data_dir / "attachments" / "versions").glob("*.png"))
    assert len(photos) == 12
    assert len({hashlib.sha256(photo.read_bytes()).digest() for photo in photos}) == 12
    assert {image_size(photo) for photo in photos} == {(640, 480)}


def test_owner_review_demo_rerun_is_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "promoted-runtime"
    data_dir.mkdir()
    database = data_dir / "snaketracker.sqlite3"
    engine = migrated_engine(database)
    HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    ).bootstrap(command_for())
    engine.dispose()
    first = seed_demo(data_dir, as_of=date(2026, 8, 15))
    with sqlite3.connect(database) as connection:
        counts_before = connection.execute(
            "SELECT count(*), max(global_position) FROM domain_events"
        ).fetchone()

    second = seed_demo(data_dir, as_of=date(2026, 8, 15))

    assert second == first
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*), max(global_position) FROM domain_events"
        ).fetchone() == counts_before


def test_owner_review_demo_requires_an_existing_promoted_database(tmp_path: Path) -> None:
    target = tmp_path / "missing-runtime"

    try:
        seed_demo(target, as_of=date(2026, 8, 15))
    except FileNotFoundError as error:
        assert "promoted database" in str(error)
    else:
        raise AssertionError("Demo seeding must require the existing promoted database.")


def test_owner_review_wrapper_targets_only_the_promoted_runtime() -> None:
    wrapper = (ROOT / "scripts/development/m6_owner_review_demo.sh").read_text(encoding="utf-8")

    assert "18087" not in wrapper
    assert "snaketracker-m6-demo" not in wrapper
    assert "runtime/phase2" in wrapper
    assert "docker compose up" not in wrapper
