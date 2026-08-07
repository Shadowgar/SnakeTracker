"""Reserved test-only projection generation strategies."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Connection

from snaketracker.platform.projections.definitions import GenerationLayout, ProjectionEvent


class OrdinaryCounterStrategy:
    def __init__(self, projection_name: str = "__snaketracker_test__.counter") -> None:
        self._projection_name = projection_name

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        table = layout.component(self._projection_name, "data")
        connection.exec_driver_sql(
            f'CREATE TABLE "{table}" (event_id INTEGER PRIMARY KEY, value INTEGER NOT NULL,'
            "household_id TEXT NOT NULL,stream_type TEXT NOT NULL,stream_id TEXT NOT NULL)"
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        connection = cast(Connection, transaction)
        table = layout.component(self._projection_name, "data")
        value = event.payload.get("value")
        stored_value = value if type(value) is int else event.global_position
        connection.execute(
            text(
                f'INSERT INTO "{table}" '
                "(event_id,value,household_id,stream_type,stream_id) "
                "VALUES (:position,:value,:household_id,:stream_type,:stream_id)"
            ),
            {
                "position": event.global_position,
                "value": stored_value,
                "household_id": str(event.household_id),
                "stream_type": event.stream_type,
                "stream_id": str(event.stream_id),
            },
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        table = layout.component(self._projection_name, "data")
        rows = connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        return {"rows": int(rows)}

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        table = layout.component(self._projection_name, "data")
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')


class FailingValidationStrategy(OrdinaryCounterStrategy):
    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        del transaction, layout
        raise ValueError("injected projection validation failure")


class FTSStrategy:
    def __init__(self, projection_name: str) -> None:
        self._projection_name = projection_name

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        content = layout.component(self._projection_name, "content")
        fts = layout.component(self._projection_name, "fts")
        connection.exec_driver_sql(
            f'CREATE TABLE "{content}" (event_id INTEGER PRIMARY KEY, title TEXT NOT NULL)'
        )
        connection.exec_driver_sql(f'CREATE VIRTUAL TABLE "{fts}" USING fts5(title)')

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        connection = cast(Connection, transaction)
        content = layout.component(self._projection_name, "content")
        fts = layout.component(self._projection_name, "fts")
        title = str(
            event.payload.get("household_name", event.payload.get("label", "owner membership"))
        )
        parameters = {"position": event.global_position, "title": title}
        connection.execute(
            text(f'INSERT INTO "{content}" (event_id,title) VALUES (:position,:title)'),
            parameters,
        )
        connection.execute(
            text(f'INSERT INTO "{fts}" (rowid,title) VALUES (:position,:title)'), parameters
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        content = layout.component(self._projection_name, "content")
        fts = layout.component(self._projection_name, "fts")
        content_rows = int(
            connection.execute(text(f'SELECT count(*) FROM "{content}"')).scalar_one()
        )
        fts_rows = int(connection.execute(text(f'SELECT count(*) FROM "{fts}"')).scalar_one())
        if content_rows != fts_rows:
            raise ValueError("FTS generation does not match its content generation.")
        connection.execute(text(f'INSERT INTO "{fts}"("{fts}") VALUES(\'optimize\')'))
        return {"content_rows": content_rows, "fts_rows": fts_rows}

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        fts = layout.component(self._projection_name, "fts")
        content = layout.component(self._projection_name, "content")
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{fts}"')
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{content}"')


class ViewStrategy(OrdinaryCounterStrategy):
    def create(self, transaction: object, layout: GenerationLayout) -> None:
        super().create(transaction, layout)
        connection = cast(Connection, transaction)
        data = layout.component(self._projection_name, "data")
        view = layout.component(self._projection_name, "view")
        connection.exec_driver_sql(f'CREATE VIEW "{view}" AS SELECT event_id,value FROM "{data}"')

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        view = layout.component(self._projection_name, "view")
        return {
            "view_rows": int(
                connection.execute(text(f'SELECT count(*) FROM "{view}"')).scalar_one()
            )
        }

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        view = layout.component(self._projection_name, "view")
        connection.exec_driver_sql(f'DROP VIEW IF EXISTS "{view}"')
        super().drop(transaction, layout)


class ParentHouseholdStrategy(OrdinaryCounterStrategy):
    pass


class ChildMembershipStrategy:
    def __init__(self, projection_name: str, parent_name: str) -> None:
        self._projection_name = projection_name
        self._parent_name = parent_name

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        child = layout.component(self._projection_name, "data")
        parent = layout.component(self._parent_name, "data")
        connection.exec_driver_sql(
            f'CREATE TABLE "{child}" (event_id INTEGER PRIMARY KEY, parent_event_id INTEGER '
            f'NOT NULL REFERENCES "{parent}"(event_id))'
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        connection = cast(Connection, transaction)
        child = layout.component(self._projection_name, "data")
        parent = layout.component(self._parent_name, "data")
        parent_id = connection.execute(text(f'SELECT min(event_id) FROM "{parent}"')).scalar_one()
        connection.execute(
            text(
                f'INSERT INTO "{child}" (event_id,parent_event_id) '
                "VALUES (:event_id,:parent_event_id)"
            ),
            {"event_id": event.global_position, "parent_event_id": parent_id},
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        child = layout.component(self._projection_name, "data")
        return {
            "children": int(
                connection.execute(text(f'SELECT count(*) FROM "{child}"')).scalar_one()
            )
        }

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        child = layout.component(self._projection_name, "data")
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{child}"')
