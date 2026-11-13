"""Populated M9 migration probe using only dependencies installed in the release image."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import command

from snaketracker.application.animals import AnimalService
from snaketracker.application.attachments import AttachmentService
from snaketracker.application.identity import ROLE_CAPABILITIES, Principal
from snaketracker.application.sharing import SharingService
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.sharing.projections import SQLAlchemySharingProjection

ROOT = Path(__file__).parents[2]
REVISION = "0028_public_photo_sharing"
PREVIOUS = "0027_bioactive_plant_care"
TABLES = ("sharing_household_current", "sharing_animal_current", "animal_album_current")


def _snapshot(engine):
    with engine.connect() as connection:
        tables = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
        ).scalars()
        return {
            table: sorted(connection.exec_driver_sql(f'SELECT * FROM "{table}"').all(), key=repr)
            for table in tables
        }


def check_public_sharing_upgrade(database: Path, root: Path = ROOT) -> None:
    fixture = runpy.run_path(ROOT / "tests/integration/test_bioactive_migration_runtime.py")
    config, engine, boot, *_ = fixture["_fixture"](database, root)
    try:
        before = _snapshot(engine)
        assert before["domain_events"] and before["enclosure_plant_current"]
        for target in (REVISION, PREVIOUS, REVISION):
            engine.dispose()
            (command.downgrade if target == PREVIOUS else command.upgrade)(config, target)
            after = _snapshot(engine)
            assert {table: after[table] for table in before} == before
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
                assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            if target == REVISION:
                assert all(after[table] == [] for table in TABLES)

        store = SQLAlchemyEventStore(engine)
        animals = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        storage = LocalAttachmentStorage(database.parent / "m9-runtime-attachments")
        projection = SQLAlchemySharingProjection(engine)
        sharing = SharingService(
            store,
            projection,
            animals=animals,
            attachments=AttachmentService(
                animals=animals,
                repository=SQLAlchemyAttachmentRepository(engine),
                storage=storage,
            ),
            storage=storage,
            free_space_reserve_bytes=0,
        )
        owner = Principal(
            boot.user_id,
            boot.household_id,
            "Owner",
            "Plant home",
            "UTC",
            "owner",
            ROLE_CAPABILITIES["owner"],
        )
        publication = sharing.configure_household(
            owner,
            enabled=False,
            title="Fictional collection",
            description="",
            slug="fictional",
            idempotency_key="runtime-private-collection",
        )
        projection.rebuild(store, owner.household_id)
        assert sharing.household(owner) == publication
        assert sharing.public_collection(publication.slug) is None
        retained = _snapshot(engine)
        engine.dispose()
        try:
            command.downgrade(config, PREVIOUS)
        except RuntimeError as error:
            assert "retained history" in str(error)
        else:
            raise AssertionError("M9 history allowed an unsafe binary downgrade")
        assert _snapshot(engine) == retained
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == REVISION
            )
    finally:
        engine.dispose()


def test_populated_public_sharing_upgrade_preserves_history_and_guards_rollback(tmp_path):
    check_public_sharing_upgrade(tmp_path / "public-sharing-runtime.sqlite3")
