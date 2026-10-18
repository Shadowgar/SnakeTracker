"""Permanent identities and bounded SQLite reference-generation operations.

All publication and promotion writers serialize with BEGIN IMMEDIATE. Search is
generation-independent for retained labels, so a new writer cannot target a discarded index.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import islice
from math import isfinite
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError

from snaketracker.application.local_taxonomy import (
    GenerationSource,
    IdentityConflict,
    TaxonAncestor,
    TaxonomyConflictError,
    TaxonomyProviderReference,
    TaxonomySearchLimitError,
    TaxonomySummary,
)
from snaketracker.application.species_directory import ProviderTaxon

CLASSIFICATION = (
    "rank",
    "kingdom",
    "phylum_division",
    "class_name",
    "order_name",
    "family",
    "genus",
    "species",
    "infra_rank",
)
LABELS = ("accepted_scientific_name", "preferred_common_name", "authorship", *CLASSIFICATION)
FACT_FIELDS = (
    *LABELS,
    "supported_group",
    "taxonomic_status",
    "provider",
    "provider_id",
    "source_url",
    "synonyms",
    "alternative_common_names",
    "parent_provider_id",
    "accepted_provider_id",
)


def execute(connection: Connection, sql: str, **parameters: Any) -> Any:
    return connection.execute(text(sql), parameters)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Taxonomy timestamps require an explicit timezone.")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def validate(candidate: ProviderTaxon) -> None:
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", candidate.provider)
        or not candidate.provider_id
        or len(candidate.provider_id) > 128
        or not candidate.accepted_scientific_name.strip()
        or len(candidate.accepted_scientific_name) > 256
        or not candidate.source_url.startswith("https://")
        or len(candidate.source_url) > 1024
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}|", candidate.supported_group)
        or candidate.taxonomic_status not in {"accepted", "inactive", "synonym", "unknown"}
    ):
        raise ValueError("Provider taxon is invalid: identity or classification.")
    for value in (getattr(candidate, field) for field in LABELS):
        if value is not None and (len(value) > 256 or not value.strip()):
            raise ValueError("Invalid taxonomy label.")
    for names in (candidate.synonyms, candidate.alternative_common_names):
        if len(names) > 64 or any(not name.strip() or len(name) > 256 for name in names):
            raise ValueError("Invalid taxonomy aliases.")
    for identifier in (candidate.parent_provider_id, candidate.accepted_provider_id):
        if identifier == candidate.provider_id:
            raise ValueError("Taxonomy relationship has a direct self-reference cycle.")
        if identifier is not None and (not identifier.strip() or len(identifier) > 128):
            raise ValueError("Invalid parent or accepted identity.")


def _facts_differ(left: dict[str, Any], right: dict[str, Any]) -> bool:
    fields = (
        *LABELS,
        "supported_group",
        "taxonomic_status",
        "synonyms",
        "alternative_common_names",
        "parent_provider_id",
        "accepted_provider_id",
    )
    return any(left.get(field) != right.get(field) for field in fields)


def validate_generation_source(source: GenerationSource) -> None:
    if (
        not source.label.strip()
        or len(source.label) > 256
        or not source.rights.strip()
        or len(source.rights) > 4096
        or not re.fullmatch(r"[a-f0-9]{64}", source.checksum)
    ):
        raise ValueError("Generation requires source, checksum and explicit rights provenance.")
    validate(ProviderTaxon(source.provider, "source", source.source_url, "", "Source validation"))
    timestamp(source.retrieved_at)
    if source.snapshot_at is not None:
        timestamp(source.snapshot_at)


class LocalTaxonomyCatalog:
    """Local taxonomy port plus explicit operator-only generation management."""

    def __init__(
        self, engine: Engine, *, search_max_candidates: int = 256, search_max_seconds: float = 1.0
    ) -> None:
        if search_max_candidates < 1 or not isfinite(search_max_seconds) or search_max_seconds <= 0:
            raise ValueError("Search requires positive finite work bounds.")
        self.engine = engine
        self._search_max_candidates = search_max_candidates
        self._search_max_seconds = search_max_seconds

    @contextmanager
    def _write(self, *, max_seconds: float | None = None) -> Iterator[Connection]:
        with self.engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            native = connection.connection.driver_connection
            assert native is not None
            deadline = time.monotonic() + max_seconds if max_seconds is not None else None
            if deadline is not None:
                native.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            try:
                yield connection
            except OperationalError as error:
                if deadline is not None and "interrupted" in str(error.orig):
                    raise ValueError(
                        "Final reconciliation exceeds its execution time bound."
                    ) from error
                raise
            finally:
                if deadline is not None:
                    native.set_progress_handler(None, 0)

    @contextmanager
    def _read(self) -> Iterator[Connection]:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            yield connection

    @staticmethod
    def _revision(connection: Connection) -> int:
        return int(
            execute(
                connection, "SELECT coalesce(max(revision),0) FROM taxonomy_changes"
            ).scalar_one()
        )

    @staticmethod
    def _change(connection: Connection, taxon_id: str, kind: str, details: str) -> int:
        return int(
            execute(
                connection,
                "INSERT INTO taxonomy_changes(taxon_id,kind,recorded_at,details) "
                "VALUES(:id,:kind,:now,:details) RETURNING revision",
                id=taxon_id,
                kind=kind,
                now=timestamp(datetime.now(UTC)),
                details=details,
            ).scalar_one()
        )

    @staticmethod
    def _conflict(
        connection: Connection,
        taxon_id: str,
        kind: str,
        details: str,
        generation: str | None = None,
    ) -> None:
        if execute(
            connection,
            "SELECT 1 FROM taxonomy_conflicts WHERE taxon_id=:id AND kind=:kind "
            "AND details=:details AND generation_id IS :generation LIMIT 1",
            id=taxon_id,
            kind=kind,
            details=details,
            generation=generation,
        ).first():
            return
        execute(
            connection,
            "INSERT INTO taxonomy_conflicts(taxon_id,kind,details,generation_id) "
            "VALUES(:id,:kind,:details,:generation)",
            id=taxon_id,
            kind=kind,
            details=details,
            generation=generation,
        )

    @staticmethod
    def _ordering_conflict(
        connection: Connection,
        identifier: str,
        kind: str,
        payload: str,
        incoming_effective: str | None,
        opposing: dict[str, Any],
        opposing_effective: str | None,
        generation: str | None = None,
    ) -> None:
        # Decisions bind to both facts and their source clocks, not retrieval time.
        # An unchanged repeat retains the decision; a new comparison needs its own.
        details = json.dumps(
            {
                "incoming": json.loads(payload),
                "incoming_effective_at": incoming_effective,
                "opposing": {field: opposing.get(field) for field in FACT_FIELDS},
                "opposing_effective_at": opposing_effective,
            },
            sort_keys=True,
        )
        LocalTaxonomyCatalog._conflict(connection, identifier, kind, details, generation)

    def _retain_observation(
        self,
        connection: Connection,
        identifier: str,
        payload: str,
        effective: str | None,
        prior: dict[str, Any],
        prior_effective: str | None,
    ) -> bool:
        differs = _facts_differ(prior, json.loads(payload))
        if prior_effective and effective:
            if prior_effective > effective:
                return True
            if prior_effective == effective and differs:
                self._ordering_conflict(
                    connection,
                    identifier,
                    "equal_freshness",
                    payload,
                    effective,
                    prior,
                    prior_effective,
                )
                return True
        elif differs:
            self._ordering_conflict(
                connection, identifier, "unknown_order", payload, effective, prior, prior_effective
            )
            return True
        elif prior_effective and not effective:
            return True
        return False

    def _reserve(
        self,
        connection: Connection,
        candidate: ProviderTaxon,
        observed: str,
        *,
        staging: bool = False,
    ) -> str:
        identifier = execute(
            connection,
            "SELECT taxon_id FROM taxon_provider_mappings "
            "WHERE provider=:provider AND provider_id=:provider_id",
            provider=candidate.provider,
            provider_id=candidate.provider_id,
        ).scalar_one_or_none()
        if identifier is not None:
            return str(identifier)
        identifier = str(uuid4())
        columns = (
            "supported_group",
            "accepted_scientific_name",
            "preferred_common_name",
            "authorship",
            "taxonomic_status",
            *CLASSIFICATION,
        )
        execute(
            connection,
            "INSERT INTO taxa(taxon_id,"
            + ",".join(columns)
            + ",taxonomy_provider,future_guide_available,created_at,refreshed_at) VALUES(:id,"
            + ",".join(":" + name for name in columns)
            + ",:provider,0,:now,:now)",
            id=identifier,
            provider=candidate.provider,
            now=observed,
            **{name: getattr(candidate, name) for name in columns},
        )
        execute(
            connection,
            "INSERT INTO taxon_provider_mappings "
            "(taxon_id,provider,provider_id,source_url,retrieved_at,refreshed_at) "
            "VALUES(:id,:provider,:provider_id,:url,:now,:now)",
            id=identifier,
            provider=candidate.provider,
            provider_id=candidate.provider_id,
            url=candidate.source_url,
            now=observed,
        )
        # A reservation carries no searchable or workflow-enabling facts.
        rowid = execute(
            connection,
            "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
            "VALUES(:id,'catalog','','')",
            id=identifier,
        ).lastrowid
        execute(
            connection,
            "INSERT INTO taxonomy_search_keys VALUES(:id,:rowid)",
            id=identifier,
            rowid=rowid,
        )
        self._change(
            connection,
            identifier,
            "snapshot_identity_reserved" if staging else "identity_reserved",
            candidate.source_url,
        )
        return identifier

    @staticmethod
    def _labels(connection: Connection, identifier: str, candidate: ProviderTaxon) -> None:
        names = [
            (candidate.accepted_scientific_name, "scientific"),
            *((name, "synonym") for name in candidate.synonyms),
            *((name, "alternative_common") for name in candidate.alternative_common_names),
        ]
        if candidate.preferred_common_name:
            names.append((candidate.preferred_common_name, "preferred_common"))
        previous = execute(
            connection,
            "SELECT name FROM taxon_names WHERE taxon_id=:id AND name_kind='scientific'",
            id=identifier,
        ).scalars()
        names.extend(
            (name, "synonym") for name in previous if name != candidate.accepted_scientific_name
        )
        for name, kind in names:
            execute(
                connection,
                "INSERT OR IGNORE INTO taxon_names "
                "(taxon_id,name,normalized_name,name_kind) VALUES(:id,:name,:normal,:kind)",
                id=identifier,
                name=name,
                normal=" ".join(name.casefold().split()),
                kind=kind,
            )
        # Search retains all identity labels, including names replaced or absent after rollback.
        retained = (
            execute(connection, "SELECT name FROM taxon_names WHERE taxon_id=:id", id=identifier)
            .scalars()
            .all()
        )
        rowid = execute(
            connection,
            "SELECT search_rowid FROM taxonomy_search_keys WHERE taxon_id=:id",
            id=identifier,
        ).scalar_one_or_none()
        previous_terms = ""
        previous_groups = ""
        if rowid is not None:
            indexed_row = execute(
                connection,
                "SELECT names,workflow_groups FROM taxonomy_search WHERE rowid=:rowid",
                rowid=rowid,
            ).first()
            if indexed_row is not None:
                previous_terms, previous_groups = indexed_row
            execute(connection, "DELETE FROM taxonomy_search WHERE rowid=:rowid", rowid=rowid)
        base = (
            execute(connection, "SELECT * FROM taxa WHERE taxon_id=:id", id=identifier)
            .mappings()
            .one()
        )
        retained_facts = [dict(base), {field: getattr(candidate, field) for field in FACT_FIELDS}]
        retained_facts.extend(
            json.loads(payload)
            for payload in execute(
                connection, "SELECT payload FROM taxonomy_overlay WHERE taxon_id=:id", id=identifier
            ).scalars()
        )
        indexed_labels = " ".join(
            [
                previous_terms,
                *retained,
                *(
                    str(fact.get(field) or "")
                    for fact in retained_facts
                    for field in CLASSIFICATION
                ),
            ]
        )
        # Keep historical classification terms alongside retained aliases. Deduplicate
        # tokens so rebuilding this row never repeatedly expands the old document.
        indexed = " ".join(
            sorted(set(re.findall(r"[^\W_]+", indexed_labels.casefold(), flags=re.UNICODE)))
        )
        groups = " ".join(
            sorted(
                set(previous_groups.split())
                | {
                    str(fact["supported_group"])
                    for fact in retained_facts
                    if fact.get("supported_group")
                }
            )
        )
        inserted = execute(
            connection,
            "INSERT INTO taxonomy_search(rowid,taxon_id,scope,names,workflow_groups) "
            "VALUES(:rowid,:id,'catalog',:names,:groups)",
            rowid=rowid,
            id=identifier,
            names=indexed,
            groups=groups,
        ).lastrowid
        execute(
            connection,
            "INSERT INTO taxonomy_search_keys VALUES(:id,:rowid) "
            "ON CONFLICT(taxon_id) DO UPDATE SET search_rowid=excluded.search_rowid",
            id=identifier,
            rowid=inserted,
        )

    @staticmethod
    def _publish_identity(
        connection: Connection,
        identifier: str,
        candidate: ProviderTaxon,
        observed: str,
        effective: str | None,
        payload: str,
    ) -> None:
        # A failed staging reservation must not supply fallback facts on first publication.
        columns = (
            "supported_group",
            "accepted_scientific_name",
            "preferred_common_name",
            "authorship",
            "taxonomic_status",
            *CLASSIFICATION,
        )
        execute(
            connection,
            "UPDATE taxa SET "
            + ",".join(name + "=:" + name for name in columns)
            + ",taxonomy_provider=:provider WHERE taxon_id=:id AND NOT EXISTS "
            "(SELECT 1 FROM taxonomy_publications WHERE taxon_id=:id)",
            id=identifier,
            provider=candidate.provider,
            **{name: getattr(candidate, name) for name in columns},
        )
        execute(
            connection,
            "UPDATE taxon_provider_mappings SET source_url=:url,"
            "retrieved_at=:observed,refreshed_at=:observed WHERE taxon_id=:id "
            "AND provider=:provider AND NOT EXISTS (SELECT 1 FROM taxonomy_publications "
            "WHERE taxon_id=:id)",
            id=identifier,
            provider=candidate.provider,
            url=candidate.source_url,
            observed=observed,
        )
        execute(
            connection,
            "INSERT OR IGNORE INTO taxonomy_publications VALUES(:id,:effective,:payload)",
            id=identifier,
            effective=effective,
            payload=payload,
        )

    def _known_provider_fact(
        self,
        connection: Connection,
        identifier: str,
        provider: str,
        generation: str | None,
        *,
        publication_generation: str | None = None,
    ) -> dict[str, Any] | None:
        # Select one coherent provider view. Historical snapshots must never be
        # mixed into a newer overlay merely because their edges once existed.
        selected = execute(
            connection,
            "SELECT payload,source_effective_at FROM taxonomy_publications "
            "WHERE taxon_id=:id AND json_extract(payload,'$.provider')=:provider "
            "UNION ALL SELECT f.payload,g.snapshot_at FROM taxonomy_facts f "
            "JOIN taxonomy_generations g USING(generation_id) "
            "WHERE f.taxon_id=:id AND f.generation_id=:publication AND g.provider=:provider "
            "AND NOT EXISTS (SELECT 1 FROM taxonomy_publications p WHERE p.taxon_id=:id) LIMIT 1",
            id=identifier,
            provider=provider,
            publication=publication_generation,
        ).first()
        snapshot = (
            execute(
                connection,
                "SELECT f.payload,g.snapshot_at AS source_effective_at FROM taxonomy_facts f "
                "JOIN taxonomy_generations g USING(generation_id) "
                "WHERE f.taxon_id=:id AND f.generation_id=:generation AND g.provider=:provider",
                id=identifier,
                generation=generation,
                provider=provider,
            ).first()
            if generation is not None
            else None
        )
        if snapshot:
            selected = snapshot
        overlay = execute(
            connection,
            "SELECT payload,source_effective_at FROM taxonomy_overlay "
            "WHERE taxon_id=:id AND provider=:provider",
            id=identifier,
            provider=provider,
        ).first()
        if overlay and not (
            selected
            and selected.source_effective_at
            and overlay.source_effective_at
            and selected.source_effective_at > overlay.source_effective_at
        ):
            selected = overlay
        return dict(json.loads(selected.payload)) if selected else None

    def _validate_relationship_view(
        self,
        connection: Connection,
        fact: dict[str, Any],
        generation: str | None,
        *,
        deadline: float | None = None,
        publication_generation: str | None = None,
    ) -> None:
        current_identity = execute(
            connection,
            "SELECT taxon_id FROM taxon_provider_mappings WHERE provider=:provider "
            "AND provider_id=:pid",
            provider=fact["provider"],
            pid=fact["provider_id"],
        ).scalar_one_or_none()
        for relationship in ("parent_provider_id", "accepted_provider_id"):
            seen = {fact["provider_id"]}
            seen_uuids = {current_identity} if current_identity else set()
            related = fact.get(relationship)
            while related:
                if deadline is not None and time.monotonic() > deadline:
                    raise ValueError("Taxonomy relationship validation exceeds its time bound.")
                if related in seen or len(seen) >= 128:
                    raise ValueError("Taxonomy live relationship cycle or depth bound.")
                seen.add(related)
                identifier = execute(
                    connection,
                    "SELECT taxon_id FROM taxon_provider_mappings "
                    "WHERE provider=:provider AND provider_id=:pid",
                    provider=fact["provider"],
                    pid=related,
                ).scalar_one_or_none()
                if identifier is None:
                    break  # Live discovery can legitimately know only part of an ancestry.
                if identifier in seen_uuids:
                    raise ValueError("Taxonomy live relationship cycle through an identity alias.")
                seen_uuids.add(identifier)
                ancestor = self._known_provider_fact(
                    connection,
                    identifier,
                    fact["provider"],
                    generation,
                    publication_generation=publication_generation,
                )
                if ancestor is None:
                    break
                related = ancestor.get(relationship)

    def _relationship_generations(
        self, connection: Connection, provider: str, *, include: str | None = None
    ) -> tuple[str | None, ...]:
        generations = list(
            execute(
                connection,
                "SELECT g.generation_id FROM taxonomy_generations g "
                "JOIN taxonomy_generation_publications p USING(generation_id) "
                "WHERE g.provider=:provider AND g.state='ready' LIMIT 129",
                provider=provider,
            ).scalars()
        )
        if (
            include is not None
            and execute(
                connection,
                "SELECT 1 FROM taxonomy_generations WHERE generation_id=:id AND provider=:provider",
                id=include,
                provider=provider,
            ).first()
        ):
            generations.append(include)
        contexts = tuple(dict.fromkeys([None, *generations]))
        if len(contexts) > 129:
            raise ValueError("Taxonomy validation exceeds the retained generation bound.")
        return contexts

    def _validate_prospective_views(
        self,
        connection: Connection,
        identifier: str,
        provider: str,
        generation: str,
        contexts: tuple[str | None, ...],
        *,
        deadline: float,
    ) -> None:
        for context in contexts:
            selected = self._known_provider_fact(
                connection, identifier, provider, context, publication_generation=generation
            )
            if selected is not None:
                self._validate_relationship_view(
                    connection,
                    selected,
                    context,
                    deadline=deadline,
                    publication_generation=generation,
                )

    def _validate_live_relationships(
        self, connection: Connection, candidate: ProviderTaxon
    ) -> None:
        fact = {field: getattr(candidate, field) for field in FACT_FIELDS}
        for generation in self._relationship_generations(connection, candidate.provider):
            self._validate_relationship_view(connection, fact, generation)

    def _validate_identity_alias(
        self, connection: Connection, identifier: str, provider: str
    ) -> None:
        # The new mapping already participates in this transaction. Check each
        # selectable rollback view separately; obsolete edges cannot coexist with
        # newer selected facts merely because both remain in durable history.
        for generation in self._relationship_generations(connection, provider):
            selected = self._known_provider_fact(connection, identifier, provider, generation)
            if selected is not None:
                self._validate_relationship_view(connection, selected, generation)

    def publish(
        self,
        candidate: ProviderTaxon,
        *,
        retrieved_at: datetime,
        source_effective_at: datetime | None = None,
    ) -> UUID:
        with self._write() as connection:
            identifier, _ = self.publish_on(
                connection,
                candidate,
                retrieved_at=retrieved_at,
                source_effective_at=source_effective_at,
            )
            return identifier

    def publish_on(
        self,
        connection: Connection,
        candidate: ProviderTaxon,
        *,
        retrieved_at: datetime,
        source_effective_at: datetime | None = None,
    ) -> tuple[UUID, bool]:
        """Publish in the caller's BEGIN IMMEDIATE transaction; report selection."""
        if not connection.in_transaction():
            raise ValueError("Taxonomy publication requires an owned write transaction.")
        validate(candidate)
        observed = timestamp(retrieved_at)
        effective = source_effective_at or candidate.source_effective_at
        effective_text = timestamp(effective) if effective else None
        payload = json.dumps(
            {field: getattr(candidate, field) for field in FACT_FIELDS}, sort_keys=True
        )
        self._validate_live_relationships(connection, candidate)
        identifier = self._reserve(connection, candidate, observed)
        previous = self._selected(connection, identifier)
        self._publish_identity(connection, identifier, candidate, observed, effective_text, payload)
        revision = self._change(
            connection,
            identifier,
            "live_observation",
            json.dumps(
                {
                    "payload": json.loads(payload),
                    "retrieved_at": observed,
                    "source_effective_at": effective_text,
                }
            ),
        )
        old = (
            execute(
                connection,
                "SELECT * FROM taxonomy_overlay WHERE taxon_id=:id AND provider=:provider",
                id=identifier,
                provider=candidate.provider,
            )
            .mappings()
            .one_or_none()
        )
        keep_old = False
        if old:
            keep_old = self._retain_observation(
                connection,
                identifier,
                payload,
                effective_text,
                json.loads(old["payload"]),
                old["source_effective_at"],
            )
        if (
            previous is not None
            and previous[0]["provider"] == candidate.provider
            # A comparable older observation can improve the durable overlay;
            # the newer selected snapshot still wins at read time.
            and not (
                effective_text
                and previous[0]["source_effective_at"]
                and previous[0]["source_effective_at"] > effective_text
            )
        ):
            keep_old = (
                self._retain_observation(
                    connection,
                    identifier,
                    payload,
                    effective_text,
                    previous[0],
                    previous[0]["source_effective_at"],
                )
                or keep_old
            )
        if not keep_old:
            execute(
                connection,
                "INSERT INTO taxonomy_overlay "
                "(taxon_id,provider,payload,retrieved_at,source_effective_at,revision) "
                "VALUES(:id,:provider,:payload,:observed,:effective,:revision) "
                "ON CONFLICT(taxon_id,provider) DO UPDATE SET payload=excluded.payload, "
                "retrieved_at=excluded.retrieved_at,"
                "source_effective_at=excluded.source_effective_at, "
                "revision=excluded.revision",
                id=identifier,
                provider=candidate.provider,
                payload=payload,
                observed=observed,
                effective=effective_text,
                revision=revision,
            )
        for snapshot in execute(
            connection,
            "SELECT f.generation_id,f.payload,g.snapshot_at,g.provider FROM taxonomy_facts f "
            "JOIN taxonomy_generations g USING(generation_id) WHERE f.taxon_id=:id",
            id=identifier,
        ):
            opposing = json.loads(snapshot.payload)
            if _facts_differ(opposing, json.loads(payload)):
                kind = None
                if snapshot.provider != candidate.provider:
                    kind = "cross_provider_order"
                elif not snapshot.snapshot_at or not effective_text:
                    kind = "unknown_order"
                elif snapshot.snapshot_at == effective_text:
                    kind = "equal_freshness"
                if kind:
                    self._ordering_conflict(
                        connection,
                        identifier,
                        kind,
                        payload,
                        effective_text,
                        opposing,
                        snapshot.snapshot_at,
                        snapshot.generation_id,
                    )
        if (
            previous is not None
            and previous[0]["provider"] != candidate.provider
            and _facts_differ(previous[0], json.loads(payload))
        ):
            self._ordering_conflict(
                connection,
                identifier,
                "cross_provider_order",
                payload,
                effective_text,
                previous[0],
                previous[0]["source_effective_at"],
            )
        for other in execute(
            connection,
            "SELECT payload,source_effective_at FROM taxonomy_overlay "
            "WHERE taxon_id=:id AND provider!=:provider",
            id=identifier,
            provider=candidate.provider,
        ):
            if _facts_differ(json.loads(other.payload), json.loads(payload)):
                self._ordering_conflict(
                    connection,
                    identifier,
                    "cross_provider_order",
                    payload,
                    effective_text,
                    json.loads(other.payload),
                    other.source_effective_at,
                )
        label_source = candidate
        if keep_old and old is not None:
            label_source = ProviderTaxon(**json.loads(old["payload"]))
        elif keep_old and previous is not None:
            retained_fact: dict[str, Any] = {field: previous[0].get(field) for field in FACT_FIELDS}
            label_source = ProviderTaxon(**retained_fact)
        self._labels(connection, identifier, label_source)
        if (
            candidate.accepted_provider_id
            and candidate.accepted_provider_id != candidate.provider_id
        ):
            self._conflict(connection, identifier, "replacement", payload)
        selected = self._selected(connection, identifier)
        selected_observation = bool(
            selected is not None
            and selected[1] == "overlay"
            and selected[0]["provider"] == candidate.provider
            and selected[0]["revision"] == revision
        )
        return UUID(identifier), selected_observation

    def map_identity(
        self,
        taxon_id: UUID,
        provider: str,
        provider_id: str,
        *,
        source_url: str,
        decided_by: str,
        reason: str,
    ) -> None:
        if not decided_by.strip() or not reason.strip():
            raise ValueError("Identity mapping requires explicit resolution provenance.")
        validate(ProviderTaxon(provider, provider_id, source_url, "", "Mapping validation"))
        conflict = False
        with self._write() as connection:
            if not execute(
                connection, "SELECT 1 FROM taxa WHERE taxon_id=:id", id=str(taxon_id)
            ).first():
                raise ValueError("Unknown permanent taxon UUID.")
            existing = execute(
                connection,
                "SELECT taxon_id FROM taxon_provider_mappings "
                "WHERE provider=:provider AND provider_id=:pid",
                provider=provider,
                pid=provider_id,
            ).scalar_one_or_none()
            details = json.dumps(
                {
                    "provider": provider,
                    "provider_id": provider_id,
                    "decided_by": decided_by,
                    "reason": reason,
                }
            )
            if existing and existing != str(taxon_id):
                conflict = True
                self._conflict(connection, str(taxon_id), "mapping_identity", details)
            elif not existing:
                execute(
                    connection,
                    "UPDATE taxa SET taxonomy_provider=:provider WHERE taxon_id=:id "
                    "AND taxonomy_provider IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM taxon_provider_mappings WHERE taxon_id=:id)",
                    id=str(taxon_id),
                    provider=provider,
                )
                execute(
                    connection,
                    "INSERT INTO taxon_provider_mappings "
                    "(taxon_id,provider,provider_id,source_url,retrieved_at,refreshed_at) "
                    "VALUES(:id,:provider,:pid,:url,:now,:now)",
                    id=str(taxon_id),
                    provider=provider,
                    pid=provider_id,
                    url=source_url,
                    now=timestamp(datetime.now(UTC)),
                )
                self._validate_identity_alias(connection, str(taxon_id), provider)
                self._change(connection, str(taxon_id), "mapping_qualified", details)
        if conflict:
            raise TaxonomyConflictError(
                "Provider mapping already belongs to a separate permanent identity."
            )

    def begin_generation(self, source: GenerationSource, *, imported_at: datetime) -> UUID:
        validate_generation_source(source)
        generation = uuid4()
        with self._write() as connection:
            execute(
                connection,
                "INSERT INTO taxonomy_generations(generation_id,label,provider,source_url,"
                "retrieved_at,"
                "snapshot_at,imported_at,checksum,rights,starting_revision,state) VALUES "
                "(:id,:label,:provider,:url,:retrieved,:snapshot,:imported,:checksum,:rights,"
                ":start,'staging')",
                id=str(generation),
                label=source.label,
                provider=source.provider,
                url=source.source_url,
                retrieved=timestamp(source.retrieved_at),
                snapshot=timestamp(source.snapshot_at) if source.snapshot_at else None,
                imported=timestamp(imported_at),
                checksum=source.checksum,
                rights=source.rights,
                start=self._revision(connection),
            )
        return generation

    def stage(self, generation: UUID, candidates: Iterable[ProviderTaxon]) -> None:
        records = tuple(islice(candidates, 501))
        if not records or len(records) > 500:
            raise ValueError("Stage between 1 and 500 taxonomy records per transaction.")
        for candidate in records:
            validate(candidate)
        with self._write() as connection:
            source = (
                execute(
                    connection,
                    "SELECT * FROM taxonomy_generations WHERE generation_id=:id",
                    id=str(generation),
                )
                .mappings()
                .one_or_none()
            )
            if not source or source["state"] != "staging":
                raise ValueError("Generation is not staging.")
            for candidate in records:
                if candidate.provider != source["provider"]:
                    raise ValueError("Generation provider namespace mismatch.")
                identifier = self._reserve(
                    connection, candidate, str(source["retrieved_at"]), staging=True
                )
                if execute(
                    connection,
                    "SELECT 1 FROM taxonomy_facts WHERE generation_id=:g AND taxon_id=:id",
                    g=str(generation),
                    id=identifier,
                ).first():
                    raise ValueError("Generation contains a duplicate provider identity.")
                payload = json.dumps(
                    {field: getattr(candidate, field) for field in FACT_FIELDS}, sort_keys=True
                )
                execute(
                    connection,
                    "INSERT INTO taxonomy_facts(generation_id,taxon_id,payload) "
                    "VALUES(:g,:id,:payload)",
                    g=str(generation),
                    id=identifier,
                    payload=payload,
                )
                previous = self._selected(connection, identifier)
                if (
                    previous is not None
                    and previous[0]["provider"] != candidate.provider
                    and _facts_differ(previous[0], json.loads(payload))
                ):
                    self._ordering_conflict(
                        connection,
                        identifier,
                        "cross_provider_order",
                        payload,
                        source["snapshot_at"],
                        previous[0],
                        previous[0]["source_effective_at"],
                        str(generation),
                    )
                overlay = execute(
                    connection,
                    "SELECT payload,source_effective_at FROM taxonomy_overlay "
                    "WHERE taxon_id=:id AND provider=:provider",
                    id=identifier,
                    provider=candidate.provider,
                ).first()
                if overlay and _facts_differ(json.loads(overlay.payload), json.loads(payload)):
                    if not source["snapshot_at"] or not overlay.source_effective_at:
                        self._ordering_conflict(
                            connection,
                            identifier,
                            "unknown_order",
                            payload,
                            source["snapshot_at"],
                            json.loads(overlay.payload),
                            overlay.source_effective_at,
                            str(generation),
                        )
                    elif source["snapshot_at"] == overlay.source_effective_at:
                        self._ordering_conflict(
                            connection,
                            identifier,
                            "equal_freshness",
                            payload,
                            source["snapshot_at"],
                            json.loads(overlay.payload),
                            overlay.source_effective_at,
                            str(generation),
                        )
                self._change(
                    connection,
                    identifier,
                    "snapshot_labels",
                    json.dumps({"generation": str(generation), "payload": json.loads(payload)}),
                )
                search_row = execute(
                    connection,
                    "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
                    "VALUES(:id,:g,:names,:groups)",
                    groups=candidate.supported_group,
                    id=identifier,
                    g=str(generation),
                    names=" ".join(
                        [
                            *(str(getattr(candidate, field) or "") for field in LABELS),
                            *candidate.synonyms,
                            *candidate.alternative_common_names,
                        ]
                    ),
                )
                execute(
                    connection,
                    "UPDATE taxonomy_facts SET search_rowid=:rowid "
                    "WHERE generation_id=:g AND taxon_id=:id",
                    rowid=search_row.lastrowid,
                    g=str(generation),
                    id=identifier,
                )
                if (
                    candidate.accepted_provider_id
                    and candidate.accepted_provider_id != candidate.provider_id
                ):
                    self._conflict(connection, identifier, "replacement", payload, str(generation))
            execute(
                connection,
                "UPDATE taxonomy_generations SET content_revision=content_revision+1 "
                "WHERE generation_id=:g",
                g=str(generation),
            )

    def validate_generation(self, generation: UUID, *, max_seconds: float = 120.0) -> None:
        started = time.monotonic()
        with self._read() as connection:
            source = execute(
                connection,
                "SELECT state,content_revision,provider FROM taxonomy_generations "
                "WHERE generation_id=:g",
                g=str(generation),
            ).first()
            if not source or source.state != "staging":
                raise ValueError("Generation is not staging.")
            contexts = self._relationship_generations(
                connection, source.provider, include=str(generation)
            )
            rows = execute(
                connection,
                "SELECT payload FROM taxonomy_facts WHERE generation_id=:g",
                g=str(generation),
            ).scalars()
            count = 0
            for payload in rows:
                count += 1
                fact = json.loads(payload)
                identifier = fact["provider_id"]
                for relationship in ("parent_provider_id", "accepted_provider_id"):
                    seen = {identifier}
                    parent = fact[relationship]
                    while parent and parent != identifier:
                        if parent in seen or len(seen) >= 128:
                            raise ValueError(
                                "Taxonomy ancestry/accepted identity cycle or depth bound."
                            )
                        if time.monotonic() - started > max_seconds:
                            raise ValueError(
                                "Taxonomy validation exceeds its execution time bound."
                            )
                        seen.add(parent)
                        ancestor = execute(
                            connection,
                            "SELECT payload FROM taxonomy_facts WHERE generation_id=:g AND "
                            "json_extract(payload,'$.provider_id')=:parent",
                            g=str(generation),
                            parent=parent,
                        ).scalar_one_or_none()
                        if ancestor is None:
                            raise ValueError(
                                "Generation has a missing parent or accepted identity."
                            )
                        parent = json.loads(ancestor)[relationship]
                    if parent == identifier:
                        raise ValueError("Taxonomy ancestry/accepted identity cycle.")
                root = execute(
                    connection,
                    "SELECT taxon_id FROM taxon_provider_mappings WHERE provider=:provider "
                    "AND provider_id=:pid",
                    provider=fact["provider"],
                    pid=fact["provider_id"],
                ).scalar_one()
                self._validate_prospective_views(
                    connection,
                    root,
                    fact["provider"],
                    str(generation),
                    contexts,
                    deadline=started + max_seconds,
                )
                if time.monotonic() - started > max_seconds:
                    raise ValueError("Taxonomy validation exceeds its execution time bound.")
            if not count:
                raise ValueError("Empty taxonomy generation.")
        # Staging remains writable during validation. Compare its content revision before sealing.
        with self._write() as connection:
            changed = execute(
                connection,
                "UPDATE taxonomy_generations SET state='ready' "
                "WHERE generation_id=:g AND state='staging' AND content_revision=:revision",
                g=str(generation),
                revision=source.content_revision,
            ).rowcount
            if changed != 1:
                raise ValueError(
                    "Generation changed during validation; validate again before promotion."
                )

    def active_generation(self) -> UUID | None:
        with self._read() as connection:
            value = execute(
                connection, "SELECT generation_id FROM taxonomy_selection WHERE singleton=1"
            ).scalar_one()
            return UUID(value) if value else None

    def promote(
        self, generation: UUID, *, max_revisions: int = 10000, max_seconds: float = 2.0
    ) -> None:
        if max_revisions < 0 or not isfinite(max_seconds) or max_seconds <= 0:
            raise ValueError("Invalid reconciliation bound.")
        with self._write(max_seconds=max_seconds) as connection:
            started = time.monotonic()
            source = (
                execute(
                    connection,
                    "SELECT * FROM taxonomy_generations WHERE generation_id=:g",
                    g=str(generation),
                )
                .mappings()
                .one_or_none()
            )
            if not source or source["state"] != "ready":
                raise ValueError("Only a validated generation can be promoted.")
            contexts = self._relationship_generations(
                connection, source["provider"], include=str(generation)
            )
            if execute(
                connection,
                "SELECT 1 FROM taxonomy_conflicts c WHERE resolved_at IS NULL "
                "AND (generation_id=:g OR (generation_id IS NULL AND taxon_id IN "
                "(SELECT taxon_id FROM taxonomy_facts WHERE generation_id=:g))) LIMIT 1",
                g=str(generation),
            ).first():
                raise TaxonomyConflictError(
                    "Resolve generation identity conflicts before promotion."
                )
            cutoff = self._revision(connection)
            # The index is durable, shared by every generation and published
            # atomically with identity.
            # Reconcile only bounded changed identities, rather than rebuilding a private A/B index.
            changes = (
                execute(
                    connection,
                    "SELECT DISTINCT taxon_id FROM taxonomy_changes "
                    "WHERE revision>:start AND revision<=:cutoff "
                    "AND kind NOT IN ('snapshot_identity_reserved','snapshot_labels') LIMIT :limit",
                    start=source["starting_revision"],
                    cutoff=cutoff,
                    limit=max_revisions + 1,
                )
                .scalars()
                .all()
            )
            if len(changes) > max_revisions:
                raise ValueError("Final reconciliation exceeds the configured identity bound.")
            invalid = execute(
                connection,
                "SELECT 1 FROM taxonomy_changes c LEFT JOIN taxa t ON t.taxon_id=c.taxon_id "
                "LEFT JOIN taxonomy_search_keys k ON k.taxon_id=c.taxon_id "
                "LEFT JOIN taxonomy_search s ON s.rowid=k.search_rowid "
                "WHERE c.revision>:start AND c.revision<=:cutoff "
                "AND c.kind NOT IN ('snapshot_identity_reserved','snapshot_labels') AND "
                "(t.taxon_id IS NULL OR k.search_rowid IS NULL "
                "OR s.rowid IS NULL OR s.taxon_id!=c.taxon_id OR s.scope!='catalog') LIMIT 1",
                start=source["starting_revision"],
                cutoff=cutoff,
            ).first()
            if invalid:
                raise ValueError(
                    "Final reconciliation found an unresolved identity or search delta."
                )
            for identifier in changes:
                self._validate_prospective_views(
                    connection,
                    identifier,
                    source["provider"],
                    str(generation),
                    contexts,
                    deadline=started + max_seconds,
                )
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise ValueError("Final reconciliation found unresolved durable references.")
            if time.monotonic() - started > max_seconds:
                raise ValueError("Final reconciliation exceeds the configured time bound.")
            # Publish first-qualified fallback facts and visibility in the pointer transaction.
            # Indexed SQL avoids constructing a catalog-sized graph in the promotion writer.
            columns = (
                "supported_group",
                "accepted_scientific_name",
                "preferred_common_name",
                "authorship",
                "taxonomic_status",
                *CLASSIFICATION,
            )
            assignments = ",".join(
                name + "=(SELECT json_extract(f.payload,'$." + name + "') FROM taxonomy_facts f "
                "WHERE f.generation_id=:g AND f.taxon_id=taxa.taxon_id)"
                for name in columns
            )
            execute(
                connection,
                "UPDATE taxa SET " + assignments + ",taxonomy_provider=:provider "
                "WHERE taxon_id IN (SELECT taxon_id FROM taxonomy_facts WHERE generation_id=:g) "
                "AND NOT EXISTS (SELECT 1 FROM taxonomy_publications p "
                "WHERE p.taxon_id=taxa.taxon_id)",
                g=str(generation),
                provider=source["provider"],
            )
            execute(
                connection,
                "UPDATE taxon_provider_mappings SET source_url=(SELECT "
                "json_extract(f.payload,'$.source_url') FROM taxonomy_facts f "
                "WHERE f.generation_id=:g AND f.taxon_id=taxon_provider_mappings.taxon_id),"
                "retrieved_at=:retrieved,refreshed_at=:retrieved WHERE provider=:provider "
                "AND taxon_id IN (SELECT taxon_id FROM taxonomy_facts WHERE generation_id=:g) "
                "AND NOT EXISTS (SELECT 1 FROM taxonomy_publications p "
                "WHERE p.taxon_id=taxon_provider_mappings.taxon_id)",
                g=str(generation),
                provider=source["provider"],
                retrieved=source["retrieved_at"],
            )
            execute(
                connection,
                "INSERT INTO taxonomy_changes(taxon_id,kind,recorded_at,details) "
                "SELECT f.taxon_id,'reference_identity_published',:now,"
                "json_object('generation',:g) FROM taxonomy_facts f "
                "WHERE f.generation_id=:g AND NOT EXISTS "
                "(SELECT 1 FROM taxonomy_publications p WHERE p.taxon_id=f.taxon_id)",
                g=str(generation),
                now=timestamp(datetime.now(UTC)),
            )
            execute(
                connection,
                "INSERT OR IGNORE INTO taxonomy_publications "
                "SELECT taxon_id,:effective,payload FROM taxonomy_facts WHERE generation_id=:g",
                g=str(generation),
                effective=source["snapshot_at"],
            )
            active_provider = execute(
                connection,
                "SELECT g.provider FROM taxonomy_selection s JOIN taxonomy_generations g "
                "USING(generation_id) WHERE s.singleton=1",
            ).scalar_one_or_none()
            if active_provider is not None and active_provider != source["provider"]:
                # A foreign reference pointer must not discard the selected preferred-provider
                # snapshot of explicitly shared identities. Retain those facts in the durable
                # information overlay, preserving original source dates and per-identity audit.
                execute(
                    connection,
                    "INSERT INTO taxonomy_changes(taxon_id,kind,recorded_at,details) "
                    "SELECT f.taxon_id,'reference_selection_retained',:now,"
                    "json_object('from_generation',f.generation_id,'to_generation',:g,"
                    "'payload',json(f.payload)) FROM taxonomy_facts f "
                    "JOIN taxonomy_selection s ON s.generation_id=f.generation_id "
                    "JOIN taxonomy_generations old USING(generation_id) "
                    "JOIN taxonomy_facts incoming ON incoming.taxon_id=f.taxon_id "
                    "AND incoming.generation_id=:g JOIN taxa t ON t.taxon_id=f.taxon_id "
                    "LEFT JOIN taxonomy_overlay o ON o.taxon_id=f.taxon_id "
                    "AND o.provider=t.taxonomy_provider WHERE t.taxonomy_provider!=:provider "
                    "AND json_extract(f.payload,'$.provider')=t.taxonomy_provider "
                    "AND (o.taxon_id IS NULL OR (old.snapshot_at IS NOT NULL "
                    "AND o.source_effective_at IS NOT NULL "
                    "AND old.snapshot_at>o.source_effective_at))",
                    g=str(generation),
                    provider=source["provider"],
                    now=timestamp(datetime.now(UTC)),
                )
                execute(
                    connection,
                    "INSERT INTO taxonomy_overlay "
                    "(taxon_id,provider,payload,retrieved_at,source_effective_at,revision) "
                    "SELECT f.taxon_id,json_extract(f.payload,'$.provider'),f.payload,"
                    "old.retrieved_at,old.snapshot_at,c.revision FROM taxonomy_changes c "
                    "JOIN taxonomy_facts f ON f.taxon_id=c.taxon_id "
                    "AND f.generation_id=json_extract(c.details,'$.from_generation') "
                    "JOIN taxonomy_generations old ON old.generation_id=f.generation_id "
                    "WHERE c.revision>:cutoff AND c.kind='reference_selection_retained' "
                    "ON CONFLICT(taxon_id,provider) DO UPDATE SET payload=excluded.payload,"
                    "retrieved_at=excluded.retrieved_at,source_effective_at=excluded.source_effective_at,"
                    "revision=excluded.revision",
                    cutoff=cutoff,
                )
                retained_contexts: dict[str, tuple[str | None, ...]] = {}
                for retained in execute(
                    connection,
                    "SELECT c.taxon_id,t.taxonomy_provider FROM taxonomy_changes c "
                    "JOIN taxa t USING(taxon_id) WHERE c.revision>:cutoff "
                    "AND c.kind='reference_selection_retained'",
                    cutoff=cutoff,
                ):
                    provider = retained.taxonomy_provider
                    if provider not in retained_contexts:
                        retained_contexts[provider] = self._relationship_generations(
                            connection, provider, include=str(generation)
                        )
                    self._validate_prospective_views(
                        connection,
                        retained.taxon_id,
                        provider,
                        str(generation),
                        retained_contexts[provider],
                        deadline=started + max_seconds,
                    )
            cutoff = self._revision(connection)
            execute(
                connection,
                "INSERT OR IGNORE INTO taxonomy_generation_publications VALUES(:g,:provenance)",
                g=str(generation),
                provenance=json.dumps(
                    {**dict(source), "publication_cutoff": cutoff}, sort_keys=True
                ),
            )
            execute(
                connection,
                "UPDATE taxonomy_selection SET generation_id=:g,reconciled_revision=:cutoff "
                "WHERE singleton=1",
                g=str(generation),
                cutoff=cutoff,
            )

    def cleanup(self, generation: UUID, *, retained_generations: set[UUID]) -> None:
        def guard(connection: Connection) -> None:
            active = execute(
                connection, "SELECT generation_id FROM taxonomy_selection"
            ).scalar_one()
            if generation in retained_generations or active == str(generation):
                raise ValueError("Active or retained generation cannot be cleaned up.")

        # Claim retirement before deleting any facts: interrupted cleanup cannot be promoted.
        with self._write() as connection:
            guard(connection)
            claimed = execute(
                connection,
                "UPDATE taxonomy_generations SET state='retiring' WHERE generation_id=:g",
                g=str(generation),
            ).rowcount
            if claimed != 1:
                raise ValueError("Unknown taxonomy generation.")
        while True:
            with self._write() as connection:
                guard(connection)
                published = execute(
                    connection,
                    "SELECT 1 FROM taxonomy_generation_publications WHERE generation_id=:g",
                    g=str(generation),
                ).first()
                rows = execute(
                    connection,
                    "SELECT taxon_id,payload,search_rowid FROM taxonomy_facts "
                    "WHERE generation_id=:g ORDER BY taxon_id LIMIT 500",
                    g=str(generation),
                ).all()
                if not rows:
                    execute(
                        connection,
                        "DELETE FROM taxonomy_generations WHERE generation_id=:g",
                        g=str(generation),
                    )
                    return
                for identifier, payload, rowid in rows:
                    if published:
                        # Merge only previously promoted facts under the shared publication lock.
                        self._labels(connection, identifier, ProviderTaxon(**json.loads(payload)))
                    execute(
                        connection, "DELETE FROM taxonomy_search WHERE rowid=:rowid", rowid=rowid
                    )
                    execute(
                        connection,
                        "DELETE FROM taxonomy_facts WHERE generation_id=:g AND taxon_id=:id",
                        g=str(generation),
                        id=identifier,
                    )

    def conflicts(self) -> tuple[IdentityConflict, ...]:
        with self._read() as connection:
            return tuple(
                IdentityConflict(
                    int(row["conflict_id"]),
                    UUID(row["taxon_id"]),
                    row["kind"],
                    row["details"],
                    UUID(row["generation_id"]) if row["generation_id"] else None,
                )
                for row in execute(
                    connection,
                    "SELECT * FROM taxonomy_conflicts "
                    "WHERE resolved_at IS NULL ORDER BY conflict_id",
                ).mappings()
            )

    def resolve_conflict(self, conflict_id: int, *, decided_by: str, reason: str) -> None:
        """Explicitly retain separate identities/current selection; never silently relink."""
        if (
            not decided_by.strip()
            or not reason.strip()
            or len(reason) > 4096
            or len(decided_by) > 256
        ):
            raise ValueError("Conflict decisions require bounded reviewer and reason.")
        with self._write() as connection:
            row = execute(
                connection,
                "SELECT taxon_id FROM taxonomy_conflicts "
                "WHERE conflict_id=:id AND resolved_at IS NULL",
                id=conflict_id,
            ).first()
            if not row:
                raise ValueError("Unknown unresolved conflict.")
            execute(
                connection,
                "UPDATE taxonomy_conflicts SET resolved_at=:now,decided_by=:who,"
                "reason=:reason WHERE conflict_id=:id",
                now=timestamp(datetime.now(UTC)),
                who=decided_by,
                reason=reason,
                id=conflict_id,
            )
            self._change(
                connection,
                row[0],
                "conflict_resolved",
                json.dumps(
                    {"conflict_id": conflict_id, "decided_by": decided_by, "reason": reason}
                ),
            )

    def _selected(
        self, connection: Connection, taxon_id: str
    ) -> tuple[dict[str, Any], str, str] | None:
        base = (
            execute(
                connection,
                "SELECT t.*,p.source_effective_at,p.payload AS catalog_payload,"
                "m.provider,m.provider_id,"
                "m.source_url,m.retrieved_at "
                "FROM taxa t JOIN taxonomy_publications p USING(taxon_id) "
                "JOIN taxon_provider_mappings m USING(taxon_id) WHERE t.taxon_id=:id "
                "ORDER BY CASE WHEN m.provider=t.taxonomy_provider THEN 0 ELSE 1 END,"
                "m.provider LIMIT 1",
                id=taxon_id,
            )
            .mappings()
            .one_or_none()
        )
        if base is None:
            return None
        selected: dict[str, Any] = dict(base)
        if base["catalog_payload"]:
            selected.update(json.loads(base["catalog_payload"]))
        else:
            # Schema-23 publications retain their qualified names in the legacy
            # table rather than a serialized first-publication payload.
            names = execute(
                connection,
                "SELECT name,name_kind FROM taxon_names WHERE taxon_id=:id "
                "ORDER BY normalized_name,name",
                id=taxon_id,
            ).all()
            selected["synonyms"] = [name for name, kind in names if kind == "synonym"]
            selected["alternative_common_names"] = [
                name for name, kind in names if kind == "alternative_common"
            ]
        selected.update(
            synonyms=selected.get("synonyms", []),
            alternative_common_names=selected.get("alternative_common_names", []),
            parent_provider_id=selected.get("parent_provider_id"),
            source_effective_at=base["source_effective_at"],
            revision=0,
        )
        state, ordering = "catalog_fallback", "selected"
        active = (
            execute(
                connection,
                "SELECT f.payload,g.retrieved_at,g.snapshot_at "
                "FROM taxonomy_facts f JOIN taxonomy_generations g USING(generation_id) "
                "JOIN taxonomy_selection s ON s.generation_id=f.generation_id WHERE f.taxon_id=:id",
                id=taxon_id,
            )
            .mappings()
            .one_or_none()
        )
        if active and json.loads(active["payload"])["provider"] == selected["provider"]:
            selected = json.loads(active["payload"])
            selected.update(
                retrieved_at=active["retrieved_at"],
                source_effective_at=active["snapshot_at"],
                revision=0,
            )
            state = "generation"
        overlays = (
            execute(
                connection,
                "SELECT o.* FROM taxonomy_overlay o JOIN taxa t USING(taxon_id) "
                "WHERE o.taxon_id=:id "
                "ORDER BY CASE WHEN o.provider=t.taxonomy_provider THEN 0 ELSE 1 END,o.provider",
                id=taxon_id,
            )
            .mappings()
            .all()
        )
        for overlay in overlays:
            fact = json.loads(overlay["payload"])
            if selected["provider"] != overlay["provider"]:
                # Foreign identities never choose facts; durable conflicts qualify decisions.
                continue
            if (
                selected["provider"] == overlay["provider"]
                and selected["source_effective_at"]
                and overlay["source_effective_at"]
                and str(selected["source_effective_at"]) > str(overlay["source_effective_at"])
            ):
                continue
            selected = fact
            selected.update(
                retrieved_at=overlay["retrieved_at"],
                source_effective_at=overlay["source_effective_at"],
                revision=overlay["revision"],
            )
            state = "overlay"
        if execute(
            connection,
            "SELECT 1 FROM taxonomy_conflicts WHERE taxon_id=:id "
            "AND resolved_at IS NULL AND kind IN ('unknown_order','equal_freshness',"
            "'cross_provider_order') AND (generation_id IS NULL OR generation_id IN "
            "(SELECT generation_id FROM taxonomy_selection)) LIMIT 1",
            id=taxon_id,
        ).first():
            ordering = "unknown_order"
        return selected, state, ordering

    def resolve_on(self, connection: Connection, taxon_id: UUID) -> TaxonomySummary | None:
        selection = self._selected(connection, str(taxon_id))
        if selection is None:
            return None
        fact, state, ordering = selection
        ancestry: list[TaxonAncestor] = []
        seen = {str(taxon_id)}
        parent = fact.get("parent_provider_id")
        provider = fact["provider"]
        relationship_generation = (
            execute(
                connection,
                "SELECT g.generation_id FROM taxonomy_selection s "
                "JOIN taxonomy_generations g USING(generation_id) WHERE g.provider=:provider",
                provider=provider,
            ).scalar_one_or_none()
            if parent
            else None
        )
        while parent and len(ancestry) < 64:
            identifier = execute(
                connection,
                "SELECT taxon_id FROM taxon_provider_mappings "
                "WHERE provider=:provider AND provider_id=:pid",
                provider=provider,
                pid=parent,
            ).scalar_one_or_none()
            if not identifier or identifier in seen:
                break
            seen.add(identifier)
            ancestor_fact = self._known_provider_fact(
                connection, identifier, provider, relationship_generation
            )
            if ancestor_fact is None:
                break
            ancestry.append(
                TaxonAncestor(
                    UUID(identifier),
                    ancestor_fact["accepted_scientific_name"],
                    ancestor_fact.get("rank"),
                )
            )
            parent = ancestor_fact.get("parent_provider_id")
        mapping_conflict = execute(
            connection,
            "SELECT 1 FROM taxonomy_conflicts WHERE taxon_id=:id "
            "AND kind='mapping_identity' AND resolved_at IS NULL LIMIT 1",
            id=str(taxon_id),
        ).first()
        references = tuple(
            TaxonomyProviderReference(
                row.provider,
                row.provider_id,
                row.source_url,
                "conflicted" if mapping_conflict else "qualified",
            )
            for row in execute(
                connection,
                "SELECT provider,provider_id,source_url FROM "
                "taxon_provider_mappings WHERE taxon_id=:id ORDER BY provider,provider_id",
                id=str(taxon_id),
            )
        )
        return TaxonomySummary(
            taxon_id,
            fact["accepted_scientific_name"],
            fact.get("preferred_common_name"),
            tuple(fact.get("synonyms", ())),
            tuple(fact.get("alternative_common_names", ())),
            fact["supported_group"] or None,
            fact["taxonomic_status"],
            tuple((field, str(fact[field])) for field in CLASSIFICATION if fact.get(field)),
            tuple(ancestry),
            fact["provider"],
            fact["provider_id"],
            fact["source_url"],
            datetime.fromisoformat(fact["retrieved_at"]),
            datetime.fromisoformat(fact["source_effective_at"])
            if fact["source_effective_at"]
            else None,
            int(fact["revision"]),
            state,
            ordering,
            references,
            authorship=fact.get("authorship"),
        )

    def resolve(self, taxon_id: UUID) -> TaxonomySummary | None:
        with self._read() as connection:
            return self.resolve_on(connection, taxon_id)

    def search_ids(
        self, connection: Connection, query: str, *, group: str | None = None, limit: int = 10
    ) -> tuple[UUID, ...]:
        tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not 2 <= len(query.strip()) <= 100 or not 1 <= limit <= 20 or not tokens:
            raise ValueError("Search requires 2-100 characters and 1-20 results.")
        if group is not None and not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", group):
            raise ValueError("Invalid taxonomy workflow group.")
        # Intersect indexed identity matches across qualified rows. An old name and newer
        # classification may live in different published generations, including after rollback.
        matches = []
        parameters = {}
        for index, token in enumerate(dict.fromkeys(tokens)):
            key = f"term{index}"
            parameters[key] = 'names : "' + token + '"*'
            matches.append(
                "SELECT taxon_id FROM taxonomy_search WHERE taxonomy_search MATCH :"
                + key
                + " AND (scope='catalog' OR scope IN "
                "(SELECT generation_id FROM taxonomy_generation_publications))"
            )
        deadline = time.monotonic() + self._search_max_seconds
        native = connection.connection.driver_connection
        assert native is not None
        message = "Search is too broad. Refine it with more of the scientific or common name."
        native.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            identifiers = (
                execute(
                    connection,
                    "WITH matches AS (" + " INTERSECT ".join(matches) + ") "
                    "SELECT m.taxon_id FROM matches m JOIN taxa t USING(taxon_id) "
                    "JOIN taxonomy_publications p USING(taxon_id) "
                    "ORDER BY t.accepted_scientific_name COLLATE NOCASE,m.taxon_id "
                    "LIMIT :candidate_limit",
                    candidate_limit=self._search_max_candidates + 1,
                    **parameters,
                )
                .scalars()
                .all()
            )
            result: list[UUID] = []
            for index, identifier in enumerate(identifiers):
                if index >= self._search_max_candidates or time.monotonic() > deadline:
                    raise TaxonomySearchLimitError(message)
                selected = self._selected(connection, identifier) if group is not None else None
                if group is None or (selected and selected[0]["supported_group"] == group):
                    result.append(UUID(identifier))
                    if len(result) >= limit:
                        break
            if time.monotonic() > deadline:
                raise TaxonomySearchLimitError(message)
            return tuple(result)
        except OperationalError as error:
            if "interrupted" in str(error.orig):
                raise TaxonomySearchLimitError(message) from error
            raise
        finally:
            native.set_progress_handler(None, 0)

    def search(
        self, query: str, *, group: str | None = None, limit: int = 10
    ) -> tuple[TaxonomySummary, ...]:
        with self._read() as connection:
            return tuple(
                summary
                for identifier in self.search_ids(connection, query, group=group, limit=limit)
                if (summary := self.resolve_on(connection, identifier)) is not None
            )
