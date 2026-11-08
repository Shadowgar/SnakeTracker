from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import text

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.attachments import AttachmentService
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.identity import ROLE_CAPABILITIES, Principal
from snaketracker.application.sharing import SharingAuthorizationError, SharingService
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.infrastructure.sharing.projections import SQLAlchemySharingProjection

ROOT = Path(__file__).parents[2]


@pytest.fixture
def sharing(tmp_path):
    database = tmp_path / "fixture.sqlite3"
    cfg = Config(ROOT / "alembic.ini")
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(cfg, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    boot = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"public-sharing-fictional-fixture-secret",
    ).bootstrap(
        BootstrapCommand(
            household_name="Private household identity",
            timezone="UTC",
            owner_email="fictional@example.test",
            owner_display_name="Private owner",
            password="fictional secure passphrase only",
            idempotency_key="sharing-bootstrap-fixture",
            correlation_id=uuid4(),
        )
    )
    principal = Principal(
        boot.user_id,
        boot.household_id,
        "Private owner",
        "Private household identity",
        "UTC",
        "owner",
        ROLE_CAPABILITIES["owner"],
    )
    store = SQLAlchemyEventStore(engine)
    animals = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
    animal = animals.register(
        RegisterAnimalCommand(
            household_id=boot.household_id,
            actor_user_id=boot.user_id,
            correlation_id=uuid4(),
            idempotency_key="animal",
            name="Secret Animal name",
            species="Private species",
            morph=None,
            genetics=None,
            sex=None,
            birth_hatch_date=None,
            acquisition_date=None,
            breeder_source=None,
            notes="Private care note",
        )
    )
    storage = LocalAttachmentStorage(tmp_path / "attachments")
    attachments = AttachmentService(
        animals=animals, repository=SQLAlchemyAttachmentRepository(engine), storage=storage
    )
    projection = SQLAlchemySharingProjection(engine)
    service = SharingService(
        store,
        projection,
        animals=animals,
        attachments=attachments,
        storage=storage,
        free_space_reserve_bytes=0,
    )
    yield service, principal, animal.animal_id, engine, store, projection
    engine.dispose()


def photo_bytes():
    buffer = BytesIO()
    image = Image.new("RGB", (24, 16), "green")
    exif = Image.Exif()
    exif[270] = "private GPS-like metadata"
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def publish(service, principal, animal_id, photo):
    collection = service.configure_household(
        principal,
        enabled=True,
        title="Public collection",
        description="Deliberate collection text",
        slug="my-collection",
        idempotency_key="collection",
    )
    service.update_photo(
        principal,
        animal_id,
        photo.media_id,
        caption="Published caption",
        position=0,
        is_public=True,
        idempotency_key="photo-public",
    )
    animal = service.configure_animal(
        principal,
        animal_id,
        is_public=True,
        title="Published Animal",
        species="Published species",
        description="Deliberately published text",
        slug="published",
        cover_media_id=photo.media_id,
        idempotency_key="animal-public",
    )
    return collection, animal


def test_three_levels_private_defaults_snapshots_and_revocation(sharing):
    service, principal, animal_id, engine, _, _ = sharing
    photo = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="Private caption",
        idempotency_key="upload",
    )
    assert service.household(principal) is None
    assert service.animal(principal, animal_id) is None
    assert not photo.is_public
    assert service.public_photo(photo.public_token) is None
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT photo_attachment_version_id FROM animal_current")
            ).scalar_one()
            is None
        )
    collection, animal = publish(service, principal, animal_id, photo)
    public = service.public_animal(animal.slug)
    assert public.title == "Published Animal"
    assert "Secret" not in repr(public) and "Private owner" not in repr(public)
    assert str(animal_id) not in repr(public) and str(principal.household_id) not in repr(public)
    assert len(service.public_collection(collection.slug).animals) == 1
    delivered = service.public_photo(photo.public_token)
    assert delivered is not None
    with Image.open(BytesIO(delivered.content)) as image:
        assert not image.getexif()
    service.update_photo(
        principal,
        animal_id,
        photo.media_id,
        caption="Private again",
        position=0,
        is_public=False,
        idempotency_key="revoke-media",
    )
    assert service.public_photo(photo.public_token) is None
    assert service.public_animal(animal.slug).profile_photo is None
    assert service.public_animal(animal.slug).photos == ()
    service.configure_household(
        principal,
        enabled=False,
        title=collection.title,
        description=collection.description,
        slug=collection.slug,
        idempotency_key="disable",
    )
    assert service.public_animal(animal.slug) is None
    assert service.public_collection(collection.slug) is None


def test_cross_household_and_viewer_mutations_are_denied(sharing):
    service, principal, animal_id, _, _, _ = sharing
    for actor in [
        replace(principal, household_id=uuid4()),
        replace(principal, role="viewer", capabilities=ROLE_CAPABILITIES["viewer"]),
    ]:
        with pytest.raises(SharingAuthorizationError):
            service.upload_photo(
                actor,
                animal_id,
                content=photo_bytes(),
                declared_media_type="image/jpeg",
                caption="",
                idempotency_key="forbidden",
            )
    assert service.photos(principal, animal_id) == ()


def test_remove_is_immutable_and_replay_preserves_revocation(sharing):
    service, principal, animal_id, engine, store, projection = sharing
    photo = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="upload",
    )
    collection, animal = publish(service, principal, animal_id, photo)
    service.remove_photo(principal, animal_id, photo.media_id, idempotency_key="remove")
    assert service.photos(principal, animal_id) == ()
    assert service.public_photo(photo.public_token) is None
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one() == 1
        )
    projection.rebuild(store, principal.household_id)
    assert service.public_photo(photo.public_token) is None
    assert service.public_animal(animal.slug).photos == ()
    assert len(service.public_collection(collection.slug).animals) == 1


def test_archive_and_restore_require_new_deliberate_publication(sharing):
    from snaketracker.application.animals import ChangeAnimalStatusCommand
    from snaketracker.application.sharing import SharingValidationError

    service, principal, animal_id, _, _, _ = sharing
    photo = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="upload",
    )
    collection, animal = publish(service, principal, animal_id, photo)
    for status in ("archived", "active"):
        service._animals.change_status(
            ChangeAnimalStatusCommand(
                principal.household_id,
                principal.user_id,
                animal_id,
                uuid4(),
                "status-" + status,
                status,
                None,
            )
        )
        assert service.public_animal(animal.slug) is None
        assert service.public_photo(photo.public_token) is None
        assert service.public_collection(collection.slug).animals == ()
        assert service.photos(principal, animal_id)[0].media_id == photo.media_id
        assert service.private_photo(principal, animal_id, photo.media_id).content
        assert not service.animal(principal, animal_id).is_public
        if status == "archived":
            with pytest.raises(SharingValidationError, match="active Animal"):
                service.update_photo(
                    principal,
                    animal_id,
                    photo.media_id,
                    caption="Archived mutation must fail",
                    position=1,
                    is_public=True,
                    idempotency_key="archived-mutation",
                )
    assert not service.animal(principal, animal_id).is_public


def test_retained_quota_includes_removed_photos_and_admits_concurrently_once(sharing):
    from concurrent.futures import ThreadPoolExecutor

    from snaketracker.application.sharing import SharingValidationError

    service, principal, animal_id, engine, _, _ = sharing
    first = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="first",
    )
    service.remove_photo(principal, animal_id, first.media_id, idempotency_key="remove-first")
    service._quota = first.size_bytes * 3 - 1

    def upload(index):
        try:
            return service.upload_photo(
                principal,
                animal_id,
                content=photo_bytes(),
                declared_media_type="image/jpeg",
                caption="",
                idempotency_key=f"concurrent-{index}",
            )
        except SharingValidationError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(upload, (1, 2)))
    assert sum(r is not None for r in results) == 1
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one() == 2
        assert c.execute(text("SELECT count(*) FROM attachment_staging")).scalar_one() == 2
    assert service._projection.retained_bytes(principal.household_id) == first.size_bytes * 2


def test_upload_idempotency_invalid_file_and_storage_reserve(sharing, monkeypatch):
    from snaketracker.application.attachments import AttachmentValidationError
    from snaketracker.platform.events.store import IdempotencyConflictError

    service, principal, animal_id, engine, _, _ = sharing
    args = {
        "content": photo_bytes(),
        "declared_media_type": "image/jpeg",
        "caption": "",
        "idempotency_key": "same",
    }
    first = service.upload_photo(principal, animal_id, **args)
    assert service.upload_photo(principal, animal_id, **args) == first
    with pytest.raises(IdempotencyConflictError):
        service.upload_photo(principal, animal_id, **{**args, "caption": "changed"})
    with pytest.raises(AttachmentValidationError):
        service.upload_photo(
            principal,
            animal_id,
            content=b"<svg onload='alert(1)'/>",
            declared_media_type="image/svg+xml",
            caption="",
            idempotency_key="malicious",
        )
    monkeypatch.setattr(service._storage, "available_bytes", lambda: 0)
    with pytest.raises(AttachmentValidationError, match="storage reserve"):
        service.upload_photo(principal, animal_id, **{**args, "idempotency_key": "reserve"})
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM attachment_staging")).scalar_one() == 1


def test_additive_migration_preserves_all_existing_rows_and_blocks_history_downgrade(sharing):
    service, principal, animal_id, engine, _, _ = sharing
    cfg = Config(ROOT / "alembic.ini")
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.downgrade(cfg, "0027_bioactive_plant_care")
    with engine.connect() as c:
        tables = (
            c.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name"
                )
            )
            .scalars()
            .all()
        )
        before = {
            t: sorted(c.exec_driver_sql(f'SELECT * FROM "{t}"').all(), key=repr) for t in tables
        }
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        after = {
            t: sorted(c.exec_driver_sql(f'SELECT * FROM "{t}"').all(), key=repr) for t in tables
        }
        assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert c.execute(text("SELECT count(*) FROM animal_album_current")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM sharing_animal_current")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM sharing_household_current")).scalar_one() == 0
    assert before == after
    service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="immutable",
    )
    with pytest.raises(RuntimeError, match="retained history"):
        command.downgrade(cfg, "0027_bioactive_plant_care")


def test_primary_and_album_share_retained_quota_and_cannot_race(sharing):
    from concurrent.futures import ThreadPoolExecutor

    from snaketracker.application.attachments import (
        AttachmentValidationError,
        FinalizeProfilePhotoCommand,
        StageProfilePhotoCommand,
    )
    from snaketracker.application.sharing import SharingValidationError

    service, principal, animal_id, engine, _, _ = sharing
    first = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="first-retained",
    )
    service.remove_photo(principal, animal_id, first.media_id, idempotency_key="remove-retained")
    limit = first.size_bytes * 3 - 1
    service._quota = limit
    service._attachments._quota = limit

    def upload(kind):
        try:
            if kind == "album":
                return service.upload_photo(
                    principal,
                    animal_id,
                    content=photo_bytes(),
                    declared_media_type="image/jpeg",
                    caption="",
                    idempotency_key="racing-album",
                )
            stage = service._attachments.stage_profile_photo(
                StageProfilePhotoCommand(
                    principal.household_id,
                    principal.user_id,
                    animal_id,
                    "racing-primary",
                    photo_bytes(),
                    "image/jpeg",
                )
            )
            return service._attachments.finalize_profile_photo(
                FinalizeProfilePhotoCommand(
                    principal.household_id,
                    principal.user_id,
                    stage.staged_attachment_id,
                    "primary-final",
                )
            )
        except (AttachmentValidationError, SharingValidationError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(upload, ("primary", "album")))
    assert sum(r is not None for r in results) == 1
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one() == 2
    assert service._projection.retained_bytes(principal.household_id) == first.size_bytes * 2


def test_primary_upload_cannot_bypass_removed_album_quota(sharing):
    from snaketracker.application.attachments import (
        AttachmentValidationError,
        StageProfilePhotoCommand,
    )

    service, principal, animal_id, _, _, _ = sharing
    photo = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="",
        idempotency_key="retained",
    )
    service.remove_photo(principal, animal_id, photo.media_id, idempotency_key="removed")
    service._attachments._quota = photo.size_bytes
    with pytest.raises(AttachmentValidationError, match="quota"):
        service._attachments.stage_profile_photo(
            StageProfilePhotoCommand(
                principal.household_id,
                principal.user_id,
                animal_id,
                "primary-bypass",
                photo_bytes(),
                "image/jpeg",
            )
        )
