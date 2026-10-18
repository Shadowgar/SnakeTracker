"""Atomic imports and offline reads for global reviewed Care Guides."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from snaketracker.application.care_guides import GuideBundle, ReviewedGuide
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog


class CareGuideImportError(ValueError):
    """The reviewed bundle cannot be safely promoted as a whole."""


def _payload(guide: ReviewedGuide) -> tuple[str, str]:
    payload = json.dumps(
        guide.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SQLAlchemyCareGuideRepository:
    """Only new global guide tables are writable through this repository."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def import_bundle(self, bundle: GuideBundle) -> tuple[int, int]:
        """Validate every guide and taxon before one atomic reference-data transaction."""
        ordered = sorted(
            bundle.guides,
            key=lambda guide: (guide.biological_group, guide.scientific_name, guide.version),
        )
        imported = 0
        identical = 0
        with self._engine.begin() as connection:
            taxon_ids: dict[tuple[str, str], str] = {}
            for guide in ordered:
                key = (guide.biological_group.value, guide.scientific_name)
                if key in taxon_ids:
                    continue
                # Indexed candidate lookup covers fallback, overlay and active generation names.
                candidates = connection.execute(
                    text(
                        "WITH candidates AS (SELECT taxon_id FROM taxa "
                        "WHERE supported_group=:group AND accepted_scientific_name=:name "
                        "UNION SELECT taxon_id FROM taxonomy_overlay "
                        "WHERE json_extract(payload,'$.supported_group')=:group "
                        "AND json_extract(payload,'$.accepted_scientific_name')=:name UNION "
                        "SELECT f.taxon_id FROM taxonomy_facts f JOIN taxonomy_selection s "
                        "ON s.generation_id=f.generation_id WHERE "
                        "json_extract(f.payload,'$.supported_group')=:group "
                        "AND json_extract(f.payload,'$.accepted_scientific_name')=:name) "
                        "SELECT taxon_id FROM candidates JOIN taxonomy_publications USING(taxon_id)"
                    ),
                    {"group": key[0], "name": key[1]},
                ).scalars()
                rows = []
                catalog = LocalTaxonomyCatalog(self._engine)
                for identifier in candidates:
                    selected = catalog.resolve_on(connection, UUID(identifier))
                    if selected is not None:
                        if selected.workflow_group == key[0] and selected.scientific_name == key[1]:
                            rows.append(identifier)
                    elif connection.execute(
                        text(
                            "SELECT 1 FROM taxa t JOIN taxonomy_publications p USING(taxon_id) "
                            "WHERE t.taxon_id=:id AND p.payload IS NULL AND supported_group=:group "
                            "AND accepted_scientific_name=:name AND NOT EXISTS "
                            "(SELECT 1 FROM taxon_provider_mappings m WHERE m.taxon_id=t.taxon_id)"
                        ),
                        {"id": identifier, "group": key[0], "name": key[1]},
                    ).first():
                        # Legacy locally qualified taxa can have no external provider mapping.
                        rows.append(identifier)
                if len(rows) != 1:
                    raise CareGuideImportError(
                        f"Expected exactly one cached Care Keeper taxon for {key[0]} {key[1]}."
                    )
                taxon_ids[key] = str(rows[0])
            planned: dict[str, int] = {}
            for guide in ordered:
                taxon_id = taxon_ids[(guide.biological_group.value, guide.scientific_name)]
                payload, digest = _payload(guide)
                existing = connection.execute(
                    text(
                        "SELECT content_sha256 FROM care_guide_versions "
                        "WHERE taxon_id=:taxon_id AND version=:version"
                    ),
                    {"taxon_id": taxon_id, "version": guide.version},
                ).scalar_one_or_none()
                if existing is not None:
                    if existing != digest:
                        raise CareGuideImportError(
                            f"Reviewed version {guide.version} changed for {guide.scientific_name}."
                        )
                    identical += 1
                    continue
                latest = planned.get(taxon_id)
                if latest is None:
                    latest = int(
                        connection.execute(
                            text(
                                "SELECT coalesce(max(version),0) FROM care_guide_versions "
                                "WHERE taxon_id=:taxon_id"
                            ),
                            {"taxon_id": taxon_id},
                        ).scalar_one()
                    )
                if guide.version != latest + 1:
                    raise CareGuideImportError(
                        f"Version {guide.version} is not the next version for "
                        f"{guide.scientific_name}."
                    )
                planned[taxon_id] = guide.version
                self._insert_guide(connection, taxon_id, guide, payload, digest)
                imported += 1
        return imported, identical

    @staticmethod
    def _insert_guide(
        connection: Connection, taxon_id: str, guide: ReviewedGuide, payload: str, digest: str
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO care_guide_versions "
                "(taxon_id,version,biological_group,created_at,reviewed_at,imported_at,"
                "content_sha256,reviewed_payload_json) VALUES "
                "(:taxon_id,:version,:group,:created_at,:reviewed_at,:imported_at,:digest,:payload)"
            ),
            {
                "taxon_id": taxon_id,
                "version": guide.version,
                "group": guide.biological_group.value,
                "created_at": guide.created_at.isoformat(),
                "reviewed_at": guide.reviewed_at.isoformat(),
                "imported_at": datetime.now(UTC).isoformat(),
                "digest": digest,
                "payload": payload,
            },
        )
        for source in guide.sources:
            connection.execute(
                text(
                    "INSERT INTO care_guide_sources "
                    "(taxon_id,version,source_id,publisher,title,url,provider_id,source_type,"
                    "retrieved_at,reviewed_at,published_at) VALUES "
                    "(:taxon_id,:version,:source_id,:publisher,:title,:url,:provider_id,:source_type,"
                    ":retrieved_at,:reviewed_at,:published_at)"
                ),
                {
                    "taxon_id": taxon_id,
                    "version": guide.version,
                    "source_id": source.source_id,
                    "publisher": source.publisher,
                    "title": source.title,
                    "url": source.url,
                    "provider_id": source.provider_id,
                    "source_type": source.source_type,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "reviewed_at": source.reviewed_at.isoformat(),
                    "published_at": (
                        source.published_at.isoformat() if source.published_at else None
                    ),
                },
            )
        for claim in guide.claims:
            connection.execute(
                text(
                    "INSERT INTO care_guide_claims "
                    "(taxon_id,version,claim_id,source_id,section,fact_key,label,value_text,"
                    "value_number,minimum,maximum,unit,qualifier,life_stage,context,caution,scope) "
                    "VALUES (:taxon_id,:version,:claim_id,:source_id,:section,:fact_key,:label,"
                    ":value_text,:value_number,:minimum,:maximum,:unit,:qualifier,:life_stage,"
                    ":context,:caution,:scope)"
                ),
                {
                    "taxon_id": taxon_id,
                    "version": guide.version,
                    **claim.model_dump(mode="json"),
                },
            )
        connection.execute(
            text(
                "INSERT INTO care_guide_current (taxon_id,version) VALUES (:taxon_id,:version) "
                "ON CONFLICT(taxon_id) DO UPDATE SET version=excluded.version"
            ),
            {"taxon_id": taxon_id, "version": guide.version},
        )

    def current(self, taxon_id: UUID) -> ReviewedGuide | None:
        with self._engine.connect() as connection:
            payload = connection.execute(
                text(
                    "SELECT v.reviewed_payload_json FROM care_guide_versions v "
                    "JOIN care_guide_current c ON c.taxon_id=v.taxon_id AND c.version=v.version "
                    "WHERE c.taxon_id=:taxon_id"
                ),
                {"taxon_id": str(taxon_id)},
            ).scalar_one_or_none()
        return ReviewedGuide.model_validate_json(payload) if payload is not None else None

    def version(self, taxon_id: UUID, version: int) -> ReviewedGuide | None:
        with self._engine.connect() as connection:
            payload = connection.execute(
                text(
                    "SELECT reviewed_payload_json FROM care_guide_versions "
                    "WHERE taxon_id=:taxon_id AND version=:version"
                ),
                {"taxon_id": str(taxon_id), "version": version},
            ).scalar_one_or_none()
        return ReviewedGuide.model_validate_json(payload) if payload is not None else None

    def versions(self, taxon_id: UUID) -> tuple[int, ...]:
        with self._engine.connect() as connection:
            values = (
                connection.execute(
                    text(
                        "SELECT version FROM care_guide_versions WHERE taxon_id=:taxon_id "
                        "ORDER BY version DESC"
                    ),
                    {"taxon_id": str(taxon_id)},
                )
                .scalars()
                .all()
            )
        return tuple(int(value) for value in values)

    def available(self, taxon_id: UUID) -> bool:
        with self._engine.connect() as connection:
            return (
                connection.execute(
                    text("SELECT 1 FROM care_guide_current WHERE taxon_id=:taxon_id"),
                    {"taxon_id": str(taxon_id)},
                ).scalar_one_or_none()
                is not None
            )
