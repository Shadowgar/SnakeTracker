"""Synchronous, replayable publication state over retained immutable photo versions."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.sharing import AlbumPhoto, AnimalPublication, HouseholdPublication
from snaketracker.domains.sharing.contracts import (
    AlbumPhotoAddedV1,
    AlbumPhotoChangedV1,
    AlbumPhotoRemovedV1,
    AnimalPublicationChangedV1,
    HouseholdPublicationChangedV1,
)
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.store import EventStore, StreamKey

_PHOTOS = (
    "SELECT m.*,v.width,v.height,v.media_type,v.size_bytes FROM animal_album_current m "
    "JOIN attachment_versions v ON v.attachment_version_id=m.attachment_version_id "
    "AND v.household_id=m.household_id "
)


class SQLAlchemySharingProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def membership_role(self, user_id: UUID, household_id: UUID) -> str | None:
        with self._engine.connect() as c:
            role = c.execute(
                text(
                    "SELECT m.role FROM authorization_memberships m JOIN users u "
                    "ON u.user_id=m.user_id WHERE m.user_id=:u AND m.household_id=:h "
                    "AND m.status='active' AND u.status='active'"
                ),
                {"u": str(user_id), "h": str(household_id)},
            ).scalar_one_or_none()
        return str(role) if role is not None else None

    def household(self, household_id: UUID) -> HouseholdPublication | None:
        return self._household("household_id=:value", str(household_id))

    def household_by_slug(self, slug: str) -> HouseholdPublication | None:
        return self._household("slug=:value", slug)

    def _household(self, clause: str, value: str) -> HouseholdPublication | None:
        with self._engine.connect() as c:
            r = (
                c.execute(
                    text("SELECT * FROM sharing_household_current WHERE " + clause),
                    {"value": value},
                )
                .mappings()
                .one_or_none()
            )
        return (
            HouseholdPublication(
                UUID(r["household_id"]), bool(r["enabled"]), r["slug"], r["title"], r["description"]
            )
            if r is not None
            else None
        )

    def animal(self, household_id: UUID, animal_id: UUID) -> AnimalPublication | None:
        with self._engine.connect() as c:
            row = (
                c.execute(
                    text(
                        "SELECT * FROM sharing_animal_current WHERE household_id=:h AND an"
                        "imal_id=:a"
                    ),
                    {"h": str(household_id), "a": str(animal_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _animal(row) if row is not None else None

    def animal_by_slug(self, slug: str) -> AnimalPublication | None:
        with self._engine.connect() as c:
            row = (
                c.execute(
                    text("SELECT * FROM sharing_animal_current WHERE slug=:slug"), {"slug": slug}
                )
                .mappings()
                .one_or_none()
            )
        return _animal(row) if row is not None else None

    def animals(self, household_id: UUID) -> tuple[AnimalPublication, ...]:
        with self._engine.connect() as c:
            rows = (
                c.execute(
                    text(
                        "SELECT * FROM sharing_animal_current WHERE household_id=:h ORDER "
                        "BY title,slug"
                    ),
                    {"h": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_animal(r) for r in rows)

    def photos(self, household_id: UUID, animal_id: UUID) -> tuple[AlbumPhoto, ...]:
        with self._engine.connect() as c:
            rows = (
                c.execute(
                    text(
                        _PHOTOS
                        + "WHERE m.household_id=:h AND m.animal_id=:a AND m.removed=0 ORDER "
                        "BY m.position,m.media_id"
                    ),
                    {"h": str(household_id), "a": str(animal_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_photo(r) for r in rows)

    def photo(self, household_id: UUID, animal_id: UUID, media_id: UUID) -> AlbumPhoto | None:
        with self._engine.connect() as c:
            row = (
                c.execute(
                    text(_PHOTOS + "WHERE m.household_id=:h AND m.animal_id=:a AND m.media_id=:m"),
                    {"h": str(household_id), "a": str(animal_id), "m": str(media_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _photo(row) if row is not None else None

    def photo_by_token(self, token: str) -> AlbumPhoto | None:
        with self._engine.connect() as c:
            row = (
                c.execute(text(_PHOTOS + "WHERE m.public_token=:token"), {"token": token})
                .mappings()
                .one_or_none()
            )
        return _photo(row) if row is not None else None

    def retained_bytes(self, household_id: UUID) -> int:
        with self._engine.connect() as c:
            total = c.execute(
                text(
                    "SELECT (SELECT coalesce(sum(size_bytes),0) FROM attachment_versio"
                    "ns WHERE household_id=:h) + "
                    "(SELECT coalesce(sum(s.size_bytes),0) FROM attachment_staging s W"
                    "HERE s.household_id=:h AND NOT EXISTS "
                    "(SELECT 1 FROM attachment_versions v WHERE v.staged_attachment_id"
                    "=s.staged_attachment_id))"
                ),
                {"h": str(household_id)},
            ).scalar_one()
        return int(total)

    def publication_current(self, household_id: UUID, animal_id: UUID) -> bool:
        """Restoring an archived Animal cannot silently restore publication."""
        with self._engine.connect() as c:
            revoked = c.execute(
                text(
                    "SELECT coalesce((SELECT max(global_position) FROM domain_events "
                    "WHERE household_id=:h AND stream_id=:a "
                    "AND event_type='animal.status_changed'),0) > "
                    "coalesce((SELECT max(e.global_position) FROM domain_events e "
                    "JOIN event_subjects s ON s.event_id=e.event_id "
                    "WHERE e.household_id=:h AND e.event_type='sharing.animal_changed' "
                    "AND s.subject_type='animal' AND s.subject_id=:a),0)"
                ),
                {"h": str(household_id), "a": str(animal_id)},
            ).scalar_one()
        return not bool(revoked)

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        c = cast(Connection, transaction)
        for event in events:
            p, h = event.payload, str(event.household_id)
            if isinstance(p, HouseholdPublicationChangedV1):
                c.execute(
                    text(
                        "INSERT INTO sharing_household_current(household_id,enabled,slug,t"
                        "itle,description) "
                        "VALUES(:h,:enabled,:slug,:title,:description) ON CONFLICT(househo"
                        "ld_id) DO UPDATE SET "
                        "enabled=excluded.enabled,slug=excluded.slug,title=excluded.title,"
                        "description=excluded.description"
                    ),
                    {
                        "h": h,
                        "enabled": p.enabled,
                        "slug": p.slug,
                        "title": p.title,
                        "description": p.description,
                    },
                )
            elif isinstance(p, AnimalPublicationChangedV1):
                c.execute(
                    text(
                        "INSERT INTO sharing_animal_current(animal_id,household_id,slug,ti"
                        "tle,species,description,is_public,cover_media_id) "
                        "VALUES(:a,:h,:slug,:title,:species,:description,:public,:cover) O"
                        "N CONFLICT(animal_id) DO UPDATE SET "
                        "slug=excluded.slug,title=excluded.title,species=excluded.species,"
                        "description=excluded.description,is_public=excluded.is_public,cov"
                        "er_media_id=excluded.cover_media_id"
                    ),
                    {
                        "a": str(p.animal_id),
                        "h": h,
                        "slug": p.slug,
                        "title": p.title,
                        "species": p.species,
                        "description": p.description,
                        "public": p.is_public,
                        "cover": str(p.cover_media_id) if p.cover_media_id else None,
                    },
                )
            elif isinstance(p, AlbumPhotoAddedV1):
                c.execute(
                    text(
                        "INSERT INTO animal_album_current(media_id,household_id,animal_id,"
                        "attachment_version_id,public_token,caption,position,is_public,rem"
                        "oved) "
                        "VALUES(:m,:h,:a,:v,:token,:caption,:position,0,0)"
                    ),
                    {
                        "m": str(p.media_id),
                        "h": h,
                        "a": str(p.animal_id),
                        "v": str(p.attachment_version_id),
                        "token": p.public_token,
                        "caption": p.caption,
                        "position": p.position,
                    },
                )
            elif isinstance(p, AlbumPhotoChangedV1):
                c.execute(
                    text(
                        "UPDATE animal_album_current SET caption=:caption,position=:positi"
                        "on,is_public=:public "
                        "WHERE household_id=:h AND animal_id=:a AND media_id=:m AND removed=0"
                    ),
                    {
                        "caption": p.caption,
                        "position": p.position,
                        "public": p.is_public,
                        "h": h,
                        "a": str(p.animal_id),
                        "m": str(p.media_id),
                    },
                )
            elif isinstance(p, AlbumPhotoRemovedV1):
                c.execute(
                    text(
                        "UPDATE animal_album_current SET removed=1,is_public=0 WHERE house"
                        "hold_id=:h AND animal_id=:a AND media_id=:m"
                    ),
                    {"h": h, "a": str(p.animal_id), "m": str(p.media_id)},
                )

    def rebuild(self, store: EventStore, household_id: UUID) -> None:
        """Reconstruct one household without changing immutable events or attachment versions."""
        events = store.load_stream(StreamKey(household_id, "sharing", household_id))
        with self._engine.begin() as c:
            for table in (
                "animal_album_current",
                "sharing_animal_current",
                "sharing_household_current",
            ):
                c.execute(
                    text(f"DELETE FROM {table} WHERE household_id=:h"), {"h": str(household_id)}
                )
            self.apply(c, events)


def _animal(r: RowMapping) -> AnimalPublication:
    return AnimalPublication(
        UUID(r["household_id"]),
        UUID(r["animal_id"]),
        r["slug"],
        r["title"],
        r["species"],
        r["description"],
        bool(r["is_public"]),
        UUID(r["cover_media_id"]) if r["cover_media_id"] else None,
    )


def _photo(r: RowMapping) -> AlbumPhoto:
    return AlbumPhoto(
        UUID(r["media_id"]),
        UUID(r["household_id"]),
        UUID(r["animal_id"]),
        UUID(r["attachment_version_id"]),
        r["public_token"],
        r["caption"],
        r["position"],
        bool(r["is_public"]),
        bool(r["removed"]),
        r["width"],
        r["height"],
        r["media_type"],
        r["size_bytes"],
    )
