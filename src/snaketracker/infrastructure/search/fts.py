"""Allow-listed FTS5 projection and household-authorized query adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from snaketracker.application.search import SearchResult, SearchUnavailableError
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.platform.projections.definitions import GenerationLayout, ProjectionEvent

PROJECTION_NAME: Final = "global_search_fts"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CORRECTION_TYPES = {
    "animal.feeding_corrected",
    "animal.weight_corrected",
    "animal.length_corrected",
    "animal.shed_corrected",
    "animal.molt_corrected",
}
_TECHNICAL_PAYLOAD_KEYS = {"capability_profile_version", "target_event_id"}


class FTSSearchProjectionStrategy:
    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = _connection(transaction)
        content = layout.component(PROJECTION_NAME, "content")
        fts = layout.component(PROJECTION_NAME, "fts")
        connection.exec_driver_sql(
            f'CREATE TABLE "{content}" ('
            "rowid INTEGER PRIMARY KEY, document_key TEXT NOT NULL UNIQUE, "
            "household_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, "
            "body TEXT NOT NULL, route TEXT NOT NULL, capability_required TEXT, "
            "effective_at TEXT, source_global_position INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            f'CREATE INDEX "{content}_household_kind" ON "{content}" (household_id,kind)'
        )
        connection.exec_driver_sql(
            f'CREATE VIRTUAL TABLE "{fts}" USING fts5('
            "title,body,tokenize='unicode61 remove_diacritics 2')"
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        connection = _connection(transaction)
        if event.event_type == "event.voided":
            target = event.payload.get("target_event_id")
            if target is not None:
                self._delete(connection, layout, f"event:{target}")
            return
        if event.event_type == "event.reinstated":
            target = event.payload.get("target_event_id")
            restored = (
                _stored_event(connection, event.household_id, str(target))
                if target is not None
                else None
            )
            if restored is None:
                return
            document = _document(restored)
            if document is None:
                return
            key, kind, title, body, route, capability = document
            self._upsert(
                connection,
                layout,
                key=f"event:{target}",
                household_id=str(event.household_id),
                kind=kind,
                title=title,
                body=body,
                route=route,
                capability=capability,
                effective_at=restored.occurred_at.isoformat(timespec="microseconds"),
                source_position=event.global_position,
            )
            return
        document = _document(event)
        if document is None:
            return
        key, kind, title, body, route, capability = document
        if event.event_type in _CORRECTION_TYPES:
            target = event.payload.get("target_event_id")
            if target is None:
                return
            key = f"event:{target}"
        self._upsert(
            connection,
            layout,
            key=key,
            household_id=str(event.household_id),
            kind=kind,
            title=title,
            body=body,
            route=route,
            capability=capability,
            effective_at=event.occurred_at.isoformat(timespec="microseconds"),
            source_position=event.global_position,
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = _connection(transaction)
        content = layout.component(PROJECTION_NAME, "content")
        fts = layout.component(PROJECTION_NAME, "fts")
        content_count = int(
            connection.execute(text(f'SELECT count(*) FROM "{content}"')).scalar_one()
        )
        fts_count = int(connection.execute(text(f'SELECT count(*) FROM "{fts}"')).scalar_one())
        if content_count != fts_count:
            raise RuntimeError("Search content and FTS indexes are inconsistent.")
        connection.exec_driver_sql(f'INSERT INTO "{fts}" ("{fts}") VALUES (\'integrity-check\')')
        return {"row_count": content_count, "fts_integrity": "ok"}

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = _connection(transaction)
        content = layout.component(PROJECTION_NAME, "content")
        fts = layout.component(PROJECTION_NAME, "fts")
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{fts}"')
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{content}"')

    @staticmethod
    def _delete(connection: Connection, layout: GenerationLayout, key: str) -> None:
        content = layout.component(PROJECTION_NAME, "content")
        fts = layout.component(PROJECTION_NAME, "fts")
        rowid = connection.execute(
            text(f'SELECT rowid FROM "{content}" WHERE document_key=:key'), {"key": key}
        ).scalar_one_or_none()
        if rowid is not None:
            connection.execute(text(f'DELETE FROM "{fts}" WHERE rowid=:rowid'), {"rowid": rowid})
            connection.execute(
                text(f'DELETE FROM "{content}" WHERE rowid=:rowid'), {"rowid": rowid}
            )

    def _upsert(
        self,
        connection: Connection,
        layout: GenerationLayout,
        *,
        key: str,
        household_id: str,
        kind: str,
        title: str,
        body: str,
        route: str,
        capability: str | None,
        effective_at: str,
        source_position: int,
    ) -> None:
        content = layout.component(PROJECTION_NAME, "content")
        fts = layout.component(PROJECTION_NAME, "fts")
        rowid = connection.execute(
            text(f'SELECT rowid FROM "{content}" WHERE document_key=:key'), {"key": key}
        ).scalar_one_or_none()
        if rowid is None:
            connection.execute(
                text(
                    f'INSERT INTO "{content}" '
                    "(document_key,household_id,kind,title,body,route,capability_required,"
                    "effective_at,source_global_position) VALUES (:key,:household,:kind,:title,"
                    ":body,:route,:capability,:effective_at,:position)"
                ),
                {
                    "key": key,
                    "household": household_id,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "route": route,
                    "capability": capability,
                    "effective_at": effective_at,
                    "position": source_position,
                },
            )
            rowid = connection.execute(text("SELECT last_insert_rowid()")).scalar_one()
        else:
            connection.execute(text(f'DELETE FROM "{fts}" WHERE rowid=:rowid'), {"rowid": rowid})
            connection.execute(
                text(
                    f'UPDATE "{content}" SET household_id=:household,kind=:kind,title=:title,'
                    "body=:body,route=:route,capability_required=:capability,"
                    "effective_at=:effective_at,source_global_position=:position WHERE rowid=:rowid"
                ),
                {
                    "rowid": rowid,
                    "household": household_id,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "route": route,
                    "capability": capability,
                    "effective_at": effective_at,
                    "position": source_position,
                },
            )
        connection.execute(
            text(f'INSERT INTO "{fts}" (rowid,title,body) VALUES (:rowid,:title,:body)'),
            {"rowid": rowid, "title": title, "body": body},
        )


class SQLAlchemyFTSSearchRepository:
    def __init__(self, engine: Engine, manager: SQLiteProjectionGenerationManager) -> None:
        self._engine = engine
        self._manager = manager

    def search(
        self,
        household_id: UUID,
        capabilities: frozenset[str],
        query: str,
        *,
        limit: int,
    ) -> tuple[SearchResult, ...]:
        terms = _terms(query)
        if not terms:
            return ()
        try:
            layout = self._manager.active_layout("search")
            content = layout.component(PROJECTION_NAME, "content")
            fts = layout.component(PROJECTION_NAME, "fts")
        except (KeyError, RuntimeError, SQLAlchemyError) as error:
            raise SearchUnavailableError("Search is rebuilding.") from error
        statement = text(
            f'SELECT c.kind,c.title,c.body,c.route,c.effective_at FROM "{fts}" f '
            f'JOIN "{content}" c ON c.rowid=f.rowid '
            f'WHERE "{fts}" MATCH :query AND c.household_id=:household '
            "AND (c.capability_required IS NULL OR c.capability_required IN :capabilities) "
            f'ORDER BY bm25("{fts}"),c.title LIMIT :limit'
        ).bindparams(bindparam("capabilities", expanding=True))
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(
                    statement,
                    {
                        "query": " AND ".join(f'"{term}"*' for term in terms),
                        "household": str(household_id),
                        "capabilities": sorted(capabilities),
                        "limit": limit,
                    },
                ).mappings()
                return tuple(
                    SearchResult(
                        kind=str(row["kind"]),
                        title=str(row["title"]),
                        body=str(row["body"]),
                        route=str(row["route"]),
                        effective_at=(
                            str(row["effective_at"]) if row["effective_at"] is not None else None
                        ),
                    )
                    for row in rows
                )
        except SQLAlchemyError as error:
            raise SearchUnavailableError("Search is rebuilding.") from error


def _document(
    event: ProjectionEvent,
) -> tuple[str, str, str, str, str, str | None] | None:
    payload = event.payload
    if event.event_type in {"animal.registered", "animal.profile_corrected"}:
        title = str(payload.get("name", event.title))
        return (
            f"animal:{event.stream_id}",
            "animal",
            title,
            _body(payload, event.notes),
            f"/animals/{event.stream_id}",
            None,
        )
    if event.event_type in {"enclosure.registered", "enclosure.profile_changed"}:
        title = str(payload.get("name", event.title))
        return (
            f"enclosure:{event.stream_id}",
            "enclosure",
            title,
            _body(payload, event.notes),
            f"/enclosures/{event.stream_id}",
            None,
        )
    if event.event_type == "inventory.item_registered":
        return (
            f"inventory:{event.stream_id}",
            "inventory",
            str(payload.get("name", event.title)),
            _body(payload, event.notes),
            f"/inventory/{event.stream_id}",
            "inventory.view",
        )
    if event.event_type.startswith("expense."):
        if event.event_type == "expense.voided":
            return None
        return (
            f"expense:{event.stream_id}",
            "expense",
            str(payload.get("category", event.title)),
            _body(payload, event.notes),
            f"/expenses/{event.stream_id}",
            "expense.view",
        )
    if event.event_type.startswith("animal.") and event.event_type not in {
        "animal.status_changed",
        "animal.enclosure_assigned",
        "animal.photo_selected",
    }:
        return (
            f"event:{event.event_id}",
            "care",
            event.title,
            _body(payload, event.notes),
            f"/animals/{event.stream_id}/timeline",
            None,
        )
    return None


def _body(payload: Mapping[str, object], notes: str | None) -> str:
    values = [
        str(value)
        for key, value in payload.items()
        if value
        and not key.endswith("_id")
        and key not in _TECHNICAL_PAYLOAD_KEYS
        and not (key == "notes" and notes)
    ]
    if notes:
        values.append(notes)
    return " · ".join(values)


def _terms(query: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(query)[:8])


def _stored_event(
    connection: Connection, household_id: UUID, event_id: str
) -> ProjectionEvent | None:
    row = (
        connection.execute(
            text(
                "SELECT event_id,global_position,household_id,stream_type,stream_id,event_type,"
                "schema_version,payload_json,occurred_at,title,description,notes "
                "FROM domain_events "
                "WHERE household_id=:household_id AND event_id=:event_id"
            ),
            {"household_id": str(household_id), "event_id": event_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return ProjectionEvent(
        event_id=UUID(str(row["event_id"])),
        global_position=int(row["global_position"]),
        household_id=UUID(str(row["household_id"])),
        stream_type=str(row["stream_type"]),
        stream_id=UUID(str(row["stream_id"])),
        event_type=str(row["event_type"]),
        schema_version=int(row["schema_version"]),
        payload=json.loads(str(row["payload_json"])),
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
        title=str(row["title"]),
        description=str(row["description"]) if row["description"] is not None else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
    )


def _connection(transaction: object) -> Connection:
    if not isinstance(transaction, Connection):
        raise TypeError("FTS projection requires a SQLAlchemy connection.")
    return transaction
