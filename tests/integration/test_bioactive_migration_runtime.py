"""Dependency-light populated SQLite probe; callable in the disposable SQLite 3.40 image."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from snaketracker.application.enclosures import (
    AddEnclosurePlantCommand,
    ChangeEnclosureBioactiveCommand,
    EnclosureService,
    RecordPlantWateringCommand,
    RegisterEnclosureCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.reminders import (
    DisableReminderRuleCommand,
    ReminderRuleService,
    SaveSubjectScheduleCommand,
)
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.operations.import_care_guides import load_bundle

ROOT = Path(__file__).parents[2]
PREVIOUS = "47f14b4790874bcf73d39331c0feb9fb4f04cbe5"


def _config(database, root):
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def _fixture(database, root):
    config = _config(database, root)
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    boot = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"disposable-bioactive-runtime-secret",
    ).bootstrap(
        BootstrapCommand(
            "Plant home",
            "UTC",
            "owner@example.test",
            "Owner",
            "correct horse battery staple",
            "bioactive-runtime-bootstrap",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    enclosures = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
    enclosure = enclosures.register(
        RegisterEnclosureCommand(
            boot.household_id,
            boot.user_id,
            uuid4(),
            "enclosure",
            "Bioactive fixture",
            "Glass terrarium",
            None,
        )
    ).enclosure_id
    plant = enclosures.add_plant(
        AddEnclosurePlantCommand(
            boot.household_id,
            boot.user_id,
            enclosure,
            uuid4(),
            "plant",
            None,
            "Manual plant",
            "Original plant",
            1,
            None,
            None,
        )
    )
    rules = ReminderRuleService(store, SQLAlchemyReminderProjection(engine))
    rules.save_subject_schedule(
        SaveSubjectScheduleCommand(
            boot.household_id,
            boot.user_id,
            uuid4(),
            "cleaning",
            0,
            "enclosure",
            enclosure,
            "cleaning",
            10,
            "2026-11-03T12:00:00+00:00",
            True,
        )
    )
    catalog, guides = LocalTaxonomyCatalog(engine), SQLAlchemyCareGuideRepository(engine)
    bundle = load_bundle(root / "reference/care-guides/reviewed-v1.json")
    for guide in bundle.guides:
        catalog.publish(
            ProviderTaxon(
                "fixture",
                guide.scientific_name,
                "https://example.test/guide",
                guide.biological_group.value,
                guide.scientific_name,
            ),
            retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
        )
    guides.import_bundle(bundle)
    return config, engine, boot, enclosures, enclosure, plant, rules


def _snapshot(engine):
    with engine.connect() as c:
        tables = c.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
        ).scalars()
        rows = {}
        for table in tables:
            columns = [
                row[1]
                for row in c.exec_driver_sql(f'PRAGMA table_info("{table}")')
                if row[1] != "bioactive" or table != "enclosure_current"
            ]
            selection = ",".join('"' + column + '"' for column in columns)
            rows[table] = sorted(
                c.exec_driver_sql(f'SELECT {selection} FROM "{table}"').all(), key=repr
            )
        triggers = c.exec_driver_sql(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ).all()
        return rows, triggers


def check_bioactive_upgrade(database: Path, root: Path = ROOT) -> None:
    config, engine, boot, enclosures, enclosure, plant, rules = _fixture(database, root)
    try:
        # Prepare a genuinely populated schema 26 fixture with no D-owned history.
        engine.dispose()
        command.downgrade(config, "0026_amphibian_care_guides")
        before = _snapshot(engine)
        for target in ("head", "0026_amphibian_care_guides", "head"):
            engine.dispose()
            (command.upgrade if target == "head" else command.downgrade)(config, target)
            assert _snapshot(engine) == before
            with engine.connect() as c:
                assert c.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
                assert c.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
                assert c.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert not enclosures.profile_for(boot.household_id, enclosure).bioactive
        assert enclosures.plant_for(boot.household_id, enclosure, plant.enclosure_plant_id) == plant
        for table in ("care_guide_versions", "care_guide_sources", "care_guide_claims"):
            try:
                with engine.begin() as c:
                    c.exec_driver_sql(f"DELETE FROM {table}")
            except IntegrityError as error:
                assert "immutable" in str(error)
            else:
                raise AssertionError("Guide immutability trigger was lost")
        # A disabled plant reminder before first watering must independently block rollback.
        rule = rules.save_subject_schedule(
            SaveSubjectScheduleCommand(
                boot.household_id,
                boot.user_id,
                uuid4(),
                "plant-schedule",
                0,
                "enclosure-plant",
                plant.enclosure_plant_id,
                "plant_watering",
                3,
                "2026-11-03T12:00:00+00:00",
                True,
            )
        )
        rules.disable(
            DisableReminderRuleCommand(
                boot.household_id,
                boot.user_id,
                rule.rule_id,
                rule.stream_version,
                rules.correlation_id_for(boot.household_id, rule.rule_id),
                "disable-plant",
                "Disabled by keeper",
            )
        )
        before = _snapshot(engine)
        engine.dispose()
        try:
            command.downgrade(config, "0026_amphibian_care_guides")
        except RuntimeError as error:
            assert "downgrade blocked" in str(error)
        else:
            raise AssertionError("Disabled plant schedule history allowed unsafe rollback")
        assert _snapshot(engine) == before
        with engine.connect() as c:
            assert (
                c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == "0027_bioactive_plant_care"
            )
        enclosures.change_bioactive(
            ChangeEnclosureBioactiveCommand(
                boot.household_id, boot.user_id, enclosure, uuid4(), "mode", True
            )
        )
        enclosures.record_plant_watering(
            RecordPlantWateringCommand(
                boot.household_id,
                boot.user_id,
                enclosure,
                plant.enclosure_plant_id,
                uuid4(),
                "watering",
                datetime.now(UTC),
                None,
            )
        )
        assert enclosures.profile_for(boot.household_id, enclosure).bioactive
    finally:
        engine.dispose()


def test_populated_bioactive_upgrade_preserves_history_and_guards_rollback(tmp_path):
    check_bioactive_upgrade(tmp_path / "bioactive-runtime.sqlite3")
