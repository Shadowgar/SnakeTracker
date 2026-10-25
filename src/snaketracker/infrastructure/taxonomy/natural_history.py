"""Bounded explicit writes and local-only reads for retained Natural History."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine

from snaketracker.application.natural_history import NaturalHistoryVersion, bound_guide_fact
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog, execute


class NaturalHistoryRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def retain(
        self, item: NaturalHistoryVersion, *, generation_context: str | None = None
    ) -> tuple[str, int]:
        with self._engine.begin() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            selected = LocalTaxonomyCatalog(self._engine).resolve_on(c, item.taxon_id)
            mapped = execute(
                c,
                "SELECT 1 FROM taxon_provider_mappings WHERE taxon_id=:id "
                "AND provider=:p AND provider_id=:pid",
                id=str(item.taxon_id),
                p=item.identity_provider,
                pid=item.identity_provider_id,
            ).first()
            if selected is None or selected.scientific_name != item.verified_name or not mapped:
                raise ValueError(
                    "Natural History source identity requires explicit matching taxonomy evidence."
                )
            for binding in item.guide_bindings:
                guide_row = execute(
                    c,
                    "SELECT content_sha256,reviewed_payload_json FROM care_guide_versions "
                    "WHERE taxon_id=:id AND version=:v",
                    id=str(item.taxon_id),
                    v=binding.guide_version,
                ).first()
                if guide_row is None or guide_row[0] != binding.guide_sha256:
                    raise ValueError("Guide binding requires an exact retained guide version.")
                from snaketracker.application.care_guides import ReviewedGuide

                guide = ReviewedGuide.model_validate_json(guide_row[1])
                claim = next((x for x in guide.claims if x.claim_id == binding.claim_id), None)
                if claim is None or claim.context != "wild" or claim.scope != item.verified_name:
                    raise ValueError("Guide binding requires a qualified wild species context.")
                if binding.life_stage != (claim.life_stage or "unspecified"):
                    raise ValueError("Guide binding must preserve original life stage.")
                source = next(x for x in guide.sources if x.source_id == claim.source_id)
                if source.url != binding.origin or (claim.qualifier or "") != binding.qualifiers:
                    raise ValueError("Guide binding must preserve original origin and qualifiers.")
                bound_guide_fact(binding, claim)
            association = execute(
                c,
                "SELECT association_id FROM natural_history_sources "
                "WHERE taxon_id=:id AND origin=:o",
                id=str(item.taxon_id),
                o=item.origin,
            ).scalar_one_or_none()
            if association is None:
                association = str(uuid4())
                execute(
                    c,
                    "INSERT INTO natural_history_sources VALUES(:a,:id,:o)",
                    a=association,
                    id=str(item.taxon_id),
                    o=item.origin,
                )
            prior = execute(
                c,
                "SELECT version,content_sha256 FROM natural_history_versions "
                "WHERE association_id=:a AND source_revision=:r",
                a=association,
                r=item.revision,
            ).first()
            if prior is not None:
                if prior[1] != item.digest:
                    raise ValueError("A retained source revision cannot be rewritten.")
                return str(association), int(prior[0])
            number = int(
                execute(
                    c,
                    "SELECT coalesce(max(version),0)+1 FROM natural_history_versions "
                    "WHERE association_id=:a",
                    a=association,
                ).scalar_one()
            )
            execute(
                c,
                "INSERT INTO natural_history_versions VALUES(:a,:v,:r,:h,:p,:g)",
                a=association,
                v=number,
                r=item.revision,
                h=item.digest,
                p=item.payload,
                g=generation_context,
            )
            return str(association), number

    def select(
        self,
        key: tuple[str, int],
        *,
        expected_revision: int,
        content_sha256: str,
        actor: str,
        reason: str,
        development: bool = False,
    ) -> None:
        self._decide(key[0], key[1], expected_revision, actor, reason, content_sha256, development)

    def withdraw(
        self, association_id: str, *, expected_revision: int, actor: str, reason: str
    ) -> None:
        self._decide(association_id, None, expected_revision, actor, reason, None, False)

    def _decide(
        self,
        association: str,
        version: int | None,
        expected: int,
        actor: str,
        reason: str,
        digest: str | None,
        development: bool,
    ) -> None:
        if not actor.strip() or len(actor) > 256 or not reason.strip() or len(reason) > 2000:
            raise ValueError("Publication requires an actor and reason.")
        with self._engine.begin() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            current = (
                execute(
                    c,
                    "SELECT revision FROM natural_history_selection WHERE association_id=:a",
                    a=association,
                ).scalar_one_or_none()
                or 0
            )
            if current != expected:
                raise ValueError("Publication revision changed; review the current selection.")
            if version is not None:
                row = execute(
                    c,
                    "SELECT payload,content_sha256 FROM natural_history_versions "
                    "WHERE association_id=:a AND version=:v",
                    a=association,
                    v=version,
                ).first()
                if (
                    row is None
                    or row[1] != digest
                    or hashlib.sha256(row[0].encode()).hexdigest() != digest
                ):
                    raise ValueError("Publication content hash does not match retained content.")
                item = NaturalHistoryVersion.model_validate_json(row[0])
                if not development and item.rights_scope != "production":
                    raise ValueError("Production source rights are not qualified.")
            execute(
                c,
                "INSERT INTO natural_history_selection VALUES(:a,:v,:r) "
                "ON CONFLICT(association_id) DO UPDATE SET version=:v,revision=:r",
                a=association,
                v=version,
                r=current + 1,
            )
            execute(
                c,
                "INSERT INTO natural_history_decisions "
                "(association_id,version,revision,actor,reason,recorded_at) "
                "VALUES(:a,:v,:r,:actor,:reason,:at)",
                a=association,
                v=version,
                r=current + 1,
                actor=actor,
                reason=reason,
                at=datetime.now(UTC).isoformat(),
            )

    def published(
        self, taxon_id: UUID, *, include_development: bool = False
    ) -> tuple[NaturalHistoryVersion, ...]:
        with self._engine.connect() as c:
            rows = execute(
                c,
                "SELECT v.payload,v.content_sha256 FROM natural_history_sources s "
                "JOIN natural_history_selection p USING(association_id) "
                "JOIN natural_history_versions v ON v.association_id=p.association_id "
                "AND v.version=p.version WHERE s.taxon_id=:id ORDER BY s.origin",
                id=str(taxon_id),
            )
            result = []
            for payload, digest in rows:
                if hashlib.sha256(payload.encode()).hexdigest() != digest:
                    raise ValueError("Retained Natural History content integrity failure.")
                item = NaturalHistoryVersion.model_validate_json(payload)
                if include_development or item.rights_scope == "production":
                    result.append(item)
            return tuple(result)

    def versions(self, taxon_id: UUID) -> tuple[NaturalHistoryVersion, ...]:
        with self._engine.connect() as c:
            return tuple(
                NaturalHistoryVersion.model_validate_json(payload)
                for payload in execute(
                    c,
                    "SELECT payload FROM natural_history_versions JOIN natural_history_sources "
                    "USING(association_id) WHERE taxon_id=:id ORDER BY origin,version",
                    id=str(taxon_id),
                ).scalars()
            )

    def decisions(self, taxon_id: UUID) -> tuple[dict[str, object], ...]:
        with self._engine.connect() as c:
            return tuple(
                dict(row._mapping)
                for row in execute(
                    c,
                    "SELECT d.* FROM natural_history_decisions d JOIN natural_history_sources s "
                    "USING(association_id) WHERE taxon_id=:id ORDER BY decision_id",
                    id=str(taxon_id),
                )
            )
