from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

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

    assert result.animal_count == 13
    assert result.enclosure_count == 11
    assert result.scenario_version == "four-group-owner-review.v1"
    assert result.snake_count == 4
    assert result.spider_count == 3
    assert result.lizard_count == 3
    assert result.scorpion_count == 3
    assert result.profile_photo_count == 13
    assert result.prediction_ready == ("Ember", "Juniper", "Nova", "Onyx", "Pearl", "Sol")
    assert result.insufficient_history_animals == ("Bramble", "Cobalt", "Pip")
    assert result.event_count >= 175
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM animal_current WHERE household_id=?",
            (result.household_id,),
        ).fetchone() == (13,)
        assert connection.execute(
            "SELECT count(*) FROM attachment_versions WHERE household_id=?",
            (result.household_id,),
        ).fetchone() == (13,)
        assert dict(
            connection.execute(
                "SELECT animal_type,count(*) FROM animal_current WHERE household_id=? "
                "GROUP BY animal_type",
                (result.household_id,),
            ).fetchall()
        ) == {"lizard": 3, "scorpion": 3, "snake": 4, "spider": 3}
        assert connection.execute(
            "SELECT count(*) FROM domain_events WHERE household_id=? AND stream_id=? "
            "AND event_type IN ('animal.molt_recorded','animal.premolt_observed') "
            "AND schema_version=2",
            (result.household_id, result.animal_ids["Onyx"]),
        ).fetchone() == (7,)
        assert connection.execute("SELECT count(*) FROM reminder_rule_current").fetchone()[0] >= 3
        assert connection.execute(
            "SELECT count(*) FROM domain_events WHERE household_id=?",
            (str(real.household_id),),
        ).fetchone() == (real_events_before,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    photos = tuple((data_dir / "attachments" / "versions").glob("*.png"))
    assert len(photos) == 13
    assert len({hashlib.sha256(photo.read_bytes()).digest() for photo in photos}) == 13
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
        assert (
            connection.execute(
                "SELECT count(*), max(global_position) FROM domain_events"
            ).fetchone()
            == counts_before
        )


def test_owner_review_demo_reset_replaces_only_the_reserved_household(tmp_path: Path) -> None:
    data_dir = tmp_path / "promoted-runtime"
    data_dir.mkdir()
    database = data_dir / "snaketracker.sqlite3"
    engine = migrated_engine(database)
    real = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"test-bootstrap-command-secret-32b",
    ).bootstrap(command_for())
    engine.dispose()
    first = seed_demo(data_dir, as_of=date(2026, 8, 15))
    old_photos = tuple((data_dir / "attachments" / "versions").glob("*.png"))
    backup_request_id = str(uuid4())
    backup_run_id = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO backup_requests "
            "(request_id,household_id,idempotency_key,command_hash,source,status,requested_at,"
            "started_at,completed_at) VALUES (?,?,?,'hash','manual','completed',?,?,?)",
            (
                backup_request_id,
                first.household_id,
                "preserved-demo-backup",
                "2026-08-15T12:00:00+00:00",
                "2026-08-15T12:00:00+00:00",
                "2026-08-15T12:01:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO backup_runs "
            "(run_id,request_id,household_id,status,started_at,completed_at,archive_path,"
            "manifest_checksum) VALUES (?,?,?,'completed',?,?,?,'checksum')",
            (
                backup_run_id,
                backup_request_id,
                first.household_id,
                "2026-08-15T12:00:00+00:00",
                "2026-08-15T12:01:00+00:00",
                str(data_dir / "backups" / "contains-shared-database"),
            ),
        )
        connection.commit()
        real_before = tuple(
            connection.execute(
                "SELECT event_id,checksum FROM domain_events WHERE household_id=? "
                "ORDER BY global_position",
                (str(real.household_id),),
            )
        )

    replacement = seed_demo(
        data_dir,
        as_of=date(2026, 8, 15),
        reset_existing=True,
    )

    assert replacement.household_id == first.household_id
    assert replacement.animal_count == 13
    assert len(tuple((data_dir / "attachments" / "versions").glob("*.png"))) == 13
    assert not any(path.exists() for path in old_photos)
    with sqlite3.connect(database) as connection:
        assert (
            tuple(
                connection.execute(
                    "SELECT event_id,checksum FROM domain_events WHERE household_id=? "
                    "ORDER BY global_position",
                    (str(real.household_id),),
                )
            )
            == real_before
        )
        assert connection.execute(
            "SELECT count(*) FROM domain_events WHERE household_id=? AND stream_type='household'",
            (replacement.household_id,),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT status,archive_path FROM backup_runs WHERE run_id=?", (backup_run_id,)
        ).fetchone() == ("completed", str(data_dir / "backups" / "contains-shared-database"))
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_owner_review_demo_recovers_after_final_verification_interruption(
    tmp_path: Path, monkeypatch
) -> None:
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

    original = seeder._require_page_text
    failed = False

    def interrupt_once(response_text: str, *, page: str, expected: tuple[str, ...]) -> None:
        nonlocal failed
        if page == "Juniper analytics" and not failed:
            failed = True
            raise RuntimeError("simulated final verification interruption")
        original(response_text, page=page, expected=expected)

    monkeypatch.setattr(seeder, "_require_page_text", interrupt_once)
    try:
        seed_demo(data_dir, as_of=date(2026, 8, 15))
    except RuntimeError as error:
        assert "simulated final verification interruption" in str(error)
    else:
        raise AssertionError("The final verification interruption must be observed.")

    monkeypatch.setattr(seeder, "_require_page_text", original)
    recovered = seed_demo(data_dir, as_of=date(2026, 8, 15))

    assert recovered.animal_count == 13
    assert recovered.enclosure_count == 11
    assert recovered.event_count >= 175
    assert (data_dir / "demo-manifest.json").is_file()


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
