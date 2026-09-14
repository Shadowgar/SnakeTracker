"""SQLite normalized cache for universal taxa and Animal links."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.species_directory import LinkedTaxon, ProviderTaxon, TaxonRecord
from snaketracker.domains.animals.contracts import AnimalTaxonLinkedV1
from snaketracker.platform.events.envelope import DomainEvent

IMAGE_LICENSES = frozenset({"cc0", "cc-by", "cc-by-sa"})


class SQLAlchemyTaxonRepository:
    """Persist provider mappings without making their IDs Care Keeper identity."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self, query: str, group: str, *, limit: int, stale_after: datetime
    ) -> tuple[TaxonRecord, ...]:
        normalized = _normalize(query)
        with self._engine.connect() as connection:
            identifiers = (
                connection.execute(
                    text(
                        "SELECT DISTINCT t.taxon_id FROM taxa t JOIN taxon_names n "
                        "ON n.taxon_id=t.taxon_id WHERE t.supported_group=:group "
                        "AND n.normalized_name LIKE :contains ORDER BY "
                        "CASE WHEN n.normalized_name LIKE :prefix THEN 0 ELSE 1 END, "
                        "t.preferred_common_name COLLATE NOCASE, "
                        "t.accepted_scientific_name COLLATE NOCASE LIMIT :limit"
                    ),
                    {
                        "group": group,
                        "contains": f"%{normalized}%",
                        "prefix": f"{normalized}%",
                        "limit": limit,
                    },
                )
                .scalars()
                .all()
            )
            return tuple(
                record
                for identifier in identifiers
                if (record := self._get(connection, UUID(str(identifier)), stale_after)) is not None
            )

    def upsert(self, candidate: ProviderTaxon, *, observed_at: datetime) -> TaxonRecord:
        _validate_candidate(candidate)
        timestamp = observed_at.astimezone(UTC).isoformat(timespec="microseconds")
        with self._engine.begin() as connection:
            mapping = connection.execute(
                text(
                    "SELECT taxon_id FROM taxon_provider_mappings "
                    "WHERE provider=:provider AND provider_id=:provider_id"
                ),
                {"provider": candidate.provider, "provider_id": candidate.provider_id},
            ).scalar_one_or_none()
            taxon_id = UUID(str(mapping)) if mapping is not None else uuid4()
            existing_name = connection.execute(
                text("SELECT accepted_scientific_name FROM taxa WHERE taxon_id=:taxon_id"),
                {"taxon_id": str(taxon_id)},
            ).scalar_one_or_none()
            connection.execute(
                text(
                    "INSERT INTO taxa (taxon_id,supported_group,accepted_scientific_name,"
                    "authorship,preferred_common_name,taxonomic_status,rank,kingdom,"
                    "phylum_division,class_name,order_name,family,genus,species,infra_rank,"
                    "future_guide_available,created_at,refreshed_at) VALUES "
                    "(:taxon_id,:supported_group,:scientific,:authorship,:common,:status,:rank,"
                    ":kingdom,:phylum,:class_name,:order_name,:family,:genus,:species,:infra_rank,"
                    "0,:created_at,:refreshed_at) ON CONFLICT(taxon_id) DO UPDATE SET "
                    "supported_group=excluded.supported_group,"
                    "accepted_scientific_name=excluded.accepted_scientific_name,"
                    "authorship=excluded.authorship,preferred_common_name=excluded.preferred_common_name,"
                    "taxonomic_status=excluded.taxonomic_status,rank=excluded.rank,kingdom=excluded.kingdom,"
                    "phylum_division=excluded.phylum_division,class_name=excluded.class_name,"
                    "order_name=excluded.order_name,family=excluded.family,genus=excluded.genus,"
                    "species=excluded.species,infra_rank=excluded.infra_rank,"
                    "refreshed_at=excluded.refreshed_at"
                ),
                {
                    "taxon_id": str(taxon_id),
                    "supported_group": candidate.supported_group,
                    "scientific": candidate.accepted_scientific_name,
                    "authorship": candidate.authorship,
                    "common": candidate.preferred_common_name,
                    "status": candidate.taxonomic_status,
                    "rank": candidate.rank,
                    "kingdom": candidate.kingdom,
                    "phylum": candidate.phylum_division,
                    "class_name": candidate.class_name,
                    "order_name": candidate.order_name,
                    "family": candidate.family,
                    "genus": candidate.genus,
                    "species": candidate.species,
                    "infra_rank": candidate.infra_rank,
                    "created_at": timestamp,
                    "refreshed_at": timestamp,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO taxon_provider_mappings "
                    "(taxon_id,provider,provider_id,source_url,retrieved_at,refreshed_at) "
                    "VALUES (:taxon_id,:provider,:provider_id,:source_url,:observed,:observed) "
                    "ON CONFLICT(provider,provider_id) DO UPDATE SET "
                    "source_url=excluded.source_url,"
                    "refreshed_at=excluded.refreshed_at"
                ),
                {
                    "taxon_id": str(taxon_id),
                    "provider": candidate.provider,
                    "provider_id": candidate.provider_id,
                    "source_url": candidate.source_url,
                    "observed": timestamp,
                },
            )
            names = [
                (candidate.accepted_scientific_name, "scientific"),
                *((name, "alternative_common") for name in candidate.alternative_common_names),
                *((name, "synonym") for name in candidate.synonyms),
            ]
            if candidate.preferred_common_name:
                names.append((candidate.preferred_common_name, "preferred_common"))
            if (
                isinstance(existing_name, str)
                and existing_name != candidate.accepted_scientific_name
            ):
                names.append((existing_name, "synonym"))
            for name, kind in names:
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO taxon_names "
                        "(taxon_id,name,normalized_name,name_kind) "
                        "VALUES (:taxon_id,:name,:normalized,:kind)"
                    ),
                    {
                        "taxon_id": str(taxon_id),
                        "name": name,
                        "normalized": _normalize(name),
                        "kind": kind,
                    },
                )
            self._store_image(connection, taxon_id, candidate)
            record = self._get(connection, taxon_id, observed_at - timedelta(0))
        if record is None:
            raise RuntimeError("Taxon cache upsert did not persist its record.")
        return record

    def get(self, taxon_id: UUID, *, stale_after: datetime) -> TaxonRecord | None:
        with self._engine.connect() as connection:
            return self._get(connection, taxon_id, stale_after)

    def linked_for(
        self, household_id: UUID, animal_id: UUID, *, stale_after: datetime
    ) -> LinkedTaxon | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM animal_taxon_current WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {"household_id": str(household_id), "animal_id": str(animal_id)},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            taxon = self._get(connection, UUID(str(row["taxon_id"])), stale_after)
            if taxon is None:
                return None
            return LinkedTaxon(
                animal_id=animal_id,
                taxon=taxon,
                confirmed_scientific_name=str(row["confirmed_scientific_name"]),
                confirmed_common_name=_optional(row["confirmed_common_name"]),
                link_event_id=UUID(str(row["link_event_id"])),
                stream_version=int(row["stream_version"]),
            )

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.event_type != "animal.taxon_linked":
                continue
            payload = cast(AnimalTaxonLinkedV1, event.payload)
            connection.execute(
                text(
                    "INSERT INTO animal_taxon_current "
                    "(household_id,animal_id,taxon_id,link_event_id,stream_version,"
                    "confirmed_scientific_name,confirmed_common_name,provider,provider_id,"
                    "linked_at) "
                    "VALUES (:household_id,:animal_id,:taxon_id,:event_id,:stream_version,"
                    ":scientific,:common,:provider,:provider_id,:linked_at) "
                    "ON CONFLICT(household_id,animal_id) DO UPDATE SET "
                    "taxon_id=excluded.taxon_id,link_event_id=excluded.link_event_id,"
                    "stream_version=excluded.stream_version,"
                    "confirmed_scientific_name=excluded.confirmed_scientific_name,"
                    "confirmed_common_name=excluded.confirmed_common_name,provider=excluded.provider,"
                    "provider_id=excluded.provider_id,linked_at=excluded.linked_at"
                ),
                {
                    "household_id": str(event.household_id),
                    "animal_id": str(event.stream_id),
                    "taxon_id": str(payload.taxon_id),
                    "event_id": str(event.event_id),
                    "stream_version": event.stream_version,
                    "scientific": payload.accepted_scientific_name,
                    "common": payload.preferred_common_name,
                    "provider": payload.provider,
                    "provider_id": payload.provider_id,
                    "linked_at": event.recorded_at.isoformat(timespec="microseconds"),
                },
            )

    def _get(
        self, connection: Connection, taxon_id: UUID, stale_after: datetime
    ) -> TaxonRecord | None:
        row = (
            connection.execute(
                text(
                    "SELECT t.*,m.provider,m.provider_id,m.source_url,m.retrieved_at,"
                    "m.refreshed_at AS provider_refreshed_at,i.source_url AS image_source_url,"
                    "i.creator AS image_creator,i.attribution AS image_attribution,"
                    "i.license_code AS image_license_code,i.license_url AS image_license_url "
                    "FROM taxa t JOIN taxon_provider_mappings m ON m.taxon_id=t.taxon_id "
                    "LEFT JOIN taxon_images i ON i.taxon_id=t.taxon_id "
                    "WHERE t.taxon_id=:taxon_id ORDER BY m.provider LIMIT 1"
                ),
                {"taxon_id": str(taxon_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        name_rows = connection.execute(
            text("SELECT name,name_kind FROM taxon_names WHERE taxon_id=:taxon_id"),
            {"taxon_id": str(taxon_id)},
        ).all()
        alternatives = tuple(str(name) for name, kind in name_rows if kind == "alternative_common")
        synonyms = tuple(str(name) for name, kind in name_rows if kind == "synonym")
        refreshed_at = _datetime(row["refreshed_at"])
        return _record(row, alternatives, synonyms, refreshed_at < stale_after)

    def _store_image(
        self, connection: Connection, taxon_id: UUID, candidate: ProviderTaxon
    ) -> None:
        fields = (
            candidate.image_source_url,
            candidate.image_creator,
            candidate.image_attribution,
            candidate.image_license_code,
            candidate.image_license_url,
        )
        if not all(fields) or candidate.image_license_code not in IMAGE_LICENSES:
            return
        connection.execute(
            text(
                "INSERT INTO taxon_images "
                "(taxon_id,source_url,creator,attribution,license_code,license_url) "
                "VALUES (:taxon_id,:source_url,:creator,:attribution,:license_code,:license_url) "
                "ON CONFLICT(taxon_id) DO UPDATE SET source_url=excluded.source_url,"
                "creator=excluded.creator,attribution=excluded.attribution,"
                "license_code=excluded.license_code,license_url=excluded.license_url"
            ),
            {
                "taxon_id": str(taxon_id),
                "source_url": candidate.image_source_url,
                "creator": candidate.image_creator,
                "attribution": candidate.image_attribution,
                "license_code": candidate.image_license_code,
                "license_url": candidate.image_license_url,
            },
        )


def _record(
    row: RowMapping, alternatives: tuple[str, ...], synonyms: tuple[str, ...], stale: bool
) -> TaxonRecord:
    return TaxonRecord(
        taxon_id=UUID(str(row["taxon_id"])),
        supported_group=str(row["supported_group"]),
        accepted_scientific_name=str(row["accepted_scientific_name"]),
        preferred_common_name=_optional(row["preferred_common_name"]),
        authorship=_optional(row["authorship"]),
        alternative_common_names=alternatives,
        synonyms=synonyms,
        taxonomic_status=str(row["taxonomic_status"]),
        rank=_optional(row["rank"]),
        kingdom=_optional(row["kingdom"]),
        phylum_division=_optional(row["phylum_division"]),
        class_name=_optional(row["class_name"]),
        order_name=_optional(row["order_name"]),
        family=_optional(row["family"]),
        genus=_optional(row["genus"]),
        species=_optional(row["species"]),
        infra_rank=_optional(row["infra_rank"]),
        provider=str(row["provider"]),
        provider_id=str(row["provider_id"]),
        source_url=str(row["source_url"]),
        retrieved_at=_datetime(row["retrieved_at"]),
        refreshed_at=_datetime(row["refreshed_at"]),
        stale=stale,
        image_source_url=_optional(row["image_source_url"]),
        image_creator=_optional(row["image_creator"]),
        image_attribution=_optional(row["image_attribution"]),
        image_license_code=_optional(row["image_license_code"]),
        image_license_url=_optional(row["image_license_url"]),
    )


def _validate_candidate(candidate: ProviderTaxon) -> None:
    if (
        candidate.supported_group not in {"snake", "lizard", "spider", "scorpion", "plant"}
        or not candidate.provider_id
        or len(candidate.provider_id) > 128
        or not candidate.accepted_scientific_name.strip()
        or len(candidate.accepted_scientific_name) > 256
        or not candidate.source_url.startswith("https://")
    ):
        raise ValueError("Provider taxon is invalid.")


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _optional(value: object) -> str | None:
    return str(value) if value is not None else None


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
