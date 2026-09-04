from __future__ import annotations

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.attachments import (
    AttachmentService,
    AttachmentValidationError,
    FinalizeProfilePhotoCommand,
    SelectProfilePhotoCommand,
    StagedProfilePhoto,
    StageProfilePhotoCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-profile-photo-test-secret-32-bytes"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_profile_photo_is_staged_finalized_immutably_and_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "profile-photos.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Photo Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="profile-photo-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        projection = SQLAlchemyAnimalCurrentProjection(engine)
        animals = AnimalService(store, projection)
        animal = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="profile-photo-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        storage = LocalAttachmentStorage(tmp_path / "attachments")
        repository = SQLAlchemyAttachmentRepository(engine)
        attachments = AttachmentService(
            animals=animals,
            repository=repository,
            storage=storage,
        )

        stage_command = StageProfilePhotoCommand(
            household_id=bootstrap.household_id,
            actor_user_id=bootstrap.user_id,
            animal_id=animal.animal_id,
            idempotency_key="stage-nyx-photo",
            content=ONE_PIXEL_PNG,
            declared_media_type="image/png",
        )
        original_lookup = repository.staged_by_idempotency

        def delayed_missing_lookup(
            household_id: UUID, actor_user_id: UUID, idempotency_key: str
        ) -> StagedProfilePhoto | None:
            existing = original_lookup(household_id, actor_user_id, idempotency_key)
            if existing is None:
                time.sleep(0.1)
            return existing

        monkeypatch.setattr(repository, "staged_by_idempotency", delayed_missing_lookup)
        with ThreadPoolExecutor(max_workers=2) as executor:
            staged_results = tuple(
                executor.map(lambda _: attachments.stage_profile_photo(stage_command), range(2))
            )
        assert staged_results[0] == staged_results[1]
        staged = staged_results[0]
        assert staged.media_type == "image/png"
        assert (staged.width, staged.height) == (1, 1)
        assert storage.staged_exists(staged.staged_attachment_id)
        assert storage.staged_attachment_ids() == frozenset({staged.staged_attachment_id})
        different_photo = BytesIO()
        Image.new("RGB", (2, 1)).save(different_photo, format="PNG")
        with pytest.raises(AttachmentValidationError, match="Idempotency key conflicts"):
            attachments.stage_profile_photo(
                StageProfilePhotoCommand(
                    household_id=bootstrap.household_id,
                    actor_user_id=bootstrap.user_id,
                    animal_id=animal.animal_id,
                    idempotency_key="stage-nyx-photo",
                    content=different_photo.getvalue(),
                    declared_media_type="image/png",
                )
            )

        finalized = attachments.finalize_profile_photo(
            FinalizeProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                staged_attachment_id=staged.staged_attachment_id,
                idempotency_key="finalize-nyx-photo",
            )
        )
        assert finalized.staged_attachment_id == staged.staged_attachment_id
        assert storage.finalized_exists(finalized.storage_key, "image/png")
        assert not storage.staged_exists(staged.staged_attachment_id)

        selected = attachments.select_profile_photo(
            SelectProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                attachment_version_id=finalized.attachment_version_id,
                correlation_id=uuid4(),
                idempotency_key="select-nyx-photo",
            )
        )
        profile = animals.profile_for(bootstrap.household_id, animal.animal_id)
        assert profile is not None
        assert profile.photo_attachment_version_id == finalized.attachment_version_id
        assert selected.event.event_type == "animal.photo_selected"
        assert [event.event_type for event in store.load_stream(animal.stream_key)] == [
            "animal.registered",
            "animal.photo_selected",
        ]
        other_household_id = uuid4()
        with pytest.raises(AttachmentValidationError):
            attachments.load_profile_photo(other_household_id, finalized.attachment_version_id)
        with pytest.raises(AttachmentValidationError):
            attachments.select_profile_photo(
                SelectProfilePhotoCommand(
                    household_id=other_household_id,
                    actor_user_id=bootstrap.user_id,
                    animal_id=animal.animal_id,
                    attachment_version_id=finalized.attachment_version_id,
                    correlation_id=uuid4(),
                    idempotency_key="cross-household-photo-selection",
                )
            )
    finally:
        engine.dispose()


def test_profile_photo_policy_is_tenant_scoped_and_cleans_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "profile-photo-policy.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Policy Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="profile-photo-policy-bootstrap",
                correlation_id=uuid4(),
            )
        )
        animals = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="profile-photo-policy-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        storage = LocalAttachmentStorage(tmp_path / "attachments")
        attachments = AttachmentService(
            animals=animals,
            repository=SQLAlchemyAttachmentRepository(engine),
            storage=storage,
        )

        for content, media_type in (
            (b"<svg><script>alert(1)</script></svg>", "image/svg+xml"),
            (ONE_PIXEL_PNG, "image/jpeg"),
            (b"x" * (5 * 1024 * 1024 + 1), "image/png"),
        ):
            with pytest.raises(AttachmentValidationError):
                attachments.stage_profile_photo(
                    StageProfilePhotoCommand(
                        household_id=bootstrap.household_id,
                        actor_user_id=bootstrap.user_id,
                        animal_id=animal.animal_id,
                        idempotency_key=f"rejected-{uuid4()}",
                        content=content,
                        declared_media_type=media_type,
                    )
                )

        oversized = BytesIO()
        Image.new("1", (8193, 1)).save(oversized, format="PNG")
        with monkeypatch.context() as image_patch:
            image_patch.setattr(
                Image.Image,
                "load",
                lambda self: (_ for _ in ()).throw(AssertionError("oversized image decoded")),
            )
            with pytest.raises(AttachmentValidationError, match="dimension limit"):
                attachments.stage_profile_photo(
                    StageProfilePhotoCommand(
                        household_id=bootstrap.household_id,
                        actor_user_id=bootstrap.user_id,
                        animal_id=animal.animal_id,
                        idempotency_key="rejected-dimensions",
                        content=oversized.getvalue(),
                        declared_media_type="image/png",
                    )
                )

        staged = attachments.stage_profile_photo(
            StageProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                idempotency_key="orphan-stage",
                content=ONE_PIXEL_PNG,
                declared_media_type="image/png",
            )
        )
        with pytest.raises(AttachmentValidationError):
            attachments.load_profile_photo(bootstrap.household_id, staged.staged_attachment_id)
        orphan_storage_key = uuid4()
        storage.finalize(staged.staged_attachment_id, orphan_storage_key, "image/png")
        assert storage.finalized_exists(orphan_storage_key, "image/png")
        untracked_staging_id = uuid4()
        storage.stage(untracked_staging_id, ONE_PIXEL_PNG)

        cleanup = attachments.cleanup_orphans(now=datetime.now(UTC) + timedelta(days=2))
        assert cleanup.discarded_staging_count == 2
        assert cleanup.discarded_orphan_version_count == 1
        assert not storage.staged_exists(staged.staged_attachment_id)
        assert not storage.staged_exists(untracked_staging_id)
        assert not storage.finalized_exists(orphan_storage_key, "image/png")
    finally:
        engine.dispose()
