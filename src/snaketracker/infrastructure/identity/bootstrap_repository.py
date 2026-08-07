"""SQLite atomic household-bootstrap repository."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from snaketracker.application.household_bootstrap import (
    AlreadyBootstrappedError,
    BootstrapConflictError,
    BootstrapResult,
    BootstrapWrite,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1
from snaketracker.platform.events.envelope import DomainEvent, canonical_event_data


class SQLAlchemyHouseholdBootstrapRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def bootstrap(self, write: BootstrapWrite) -> BootstrapResult:
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                existing = self._existing_operation(connection, write)
                if existing is not None:
                    connection.rollback()
                    if existing["command_hash"] != write.command_hash:
                        raise BootstrapConflictError(
                            "Bootstrap idempotency key conflicts with prior use."
                        )
                    data = json.loads(existing["stored_result_json"])
                    return BootstrapResult(
                        household_id=write.result.household_id.__class__(data["household_id"]),
                        user_id=write.result.user_id.__class__(data["user_id"]),
                    )
                if connection.execute(text("SELECT count(*) FROM users")).scalar_one() != 0:
                    raise AlreadyBootstrappedError("Initial household setup is already complete.")
                self._insert_user(connection, write)
                self._insert_stream(connection, write)
                positions = [self._insert_event(connection, event) for event in write.events]
                self._insert_household_summary(connection, write, positions[0])
                self._insert_membership(connection, write, positions[1])
                self._insert_operation(connection, write)
                self._insert_audit(connection, write)
                connection.commit()
                return write.result
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _existing_operation(connection: Connection, write: BootstrapWrite) -> Any:
        return (
            connection.execute(
                text(
                    "SELECT command_hash, stored_result_json FROM idempotency_operations "
                    "WHERE household_id=:household_id AND actor_user_id=:actor_user_id "
                    "AND operation_scope='household.bootstrap' AND idempotency_key=:key"
                ),
                {
                    "household_id": str(write.result.household_id),
                    "actor_user_id": str(write.result.user_id),
                    "key": write.idempotency_key,
                },
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _insert_user(connection: Connection, write: BootstrapWrite) -> None:
        timestamp = write.recorded_at.isoformat(timespec="microseconds")
        connection.execute(
            text(
                "INSERT INTO users (user_id,email_normalized,display_name,password_hash,"
                "password_scheme,status,created_at,updated_at) "
                "VALUES (:user_id,:email,:display_name,:password_hash,'argon2id','active',"
                ":now,:now)"
            ),
            {
                "user_id": str(write.result.user_id),
                "email": write.email_normalized,
                "display_name": write.owner_display_name,
                "password_hash": write.password_hash,
                "now": timestamp,
            },
        )

    @staticmethod
    def _insert_stream(connection: Connection, write: BootstrapWrite) -> None:
        timestamp = write.recorded_at.isoformat(timespec="microseconds")
        connection.execute(
            text(
                "INSERT INTO event_streams "
                "(household_id,stream_type,stream_id,current_version,created_at,updated_at) "
                "VALUES (:household_id,'household',:household_id,2,:now,:now)"
            ),
            {"household_id": str(write.result.household_id), "now": timestamp},
        )

    @staticmethod
    def _insert_event(connection: Connection, event: DomainEvent) -> int:
        canonical = canonical_event_data(event)
        payload_json = json.dumps(canonical["payload"], sort_keys=True, separators=(",", ":"))
        result = connection.execute(
            text(
                "INSERT INTO domain_events "
                "(event_id,household_id,stream_type,stream_id,stream_version,event_type,"
                "schema_version,occurred_at,recorded_at,actor_user_id,correlation_id,causation_id,"
                "idempotency_key,title,description,payload_json,metadata_json,notes,checksum) "
                "VALUES (:event_id,:household_id,:stream_type,:stream_id,:stream_version,"
                ":event_type,:schema_version,:occurred_at,:recorded_at,:actor_user_id,"
                ":correlation_id,:causation_id,:idempotency_key,:title,:description,:payload_json,"
                ":metadata_json,:notes,:checksum)"
            ),
            {
                **canonical,
                "payload_json": payload_json,
                "metadata_json": json.dumps(canonical["metadata"], sort_keys=True),
                "checksum": event.checksum,
            },
        )
        for subject in event.subjects:
            connection.execute(
                text(
                    "INSERT INTO event_subjects "
                    "(event_id,subject_type,subject_id,relationship,display_order) "
                    "VALUES (:event_id,:subject_type,:subject_id,:relationship,:display_order)"
                ),
                {
                    "event_id": str(event.event_id),
                    "subject_type": subject.subject_type,
                    "subject_id": str(subject.subject_id),
                    "relationship": subject.relationship,
                    "display_order": subject.display_order,
                },
            )
        if result.lastrowid is None:
            raise IntegrityError("domain event did not receive a global position", {}, None)
        return int(result.lastrowid)

    @staticmethod
    def _insert_household_summary(
        connection: Connection, write: BootstrapWrite, global_position: int
    ) -> None:
        event = write.events[0]
        payload = event.payload
        if not isinstance(payload, HouseholdCreatedV1):
            raise TypeError("Household bootstrap requires a household-created payload.")
        timestamp = write.recorded_at.isoformat(timespec="microseconds")
        connection.execute(
            text(
                "INSERT INTO household_summaries "
                "(household_id,name,timezone,source_stream_version,source_global_position,"
                "created_at,updated_at) "
                "VALUES (:household_id,:name,:timezone,1,:position,:now,:now)"
            ),
            {
                "household_id": str(write.result.household_id),
                "name": payload.household_name,
                "timezone": payload.timezone,
                "position": global_position,
                "now": timestamp,
            },
        )

    @staticmethod
    def _insert_membership(
        connection: Connection, write: BootstrapWrite, global_position: int
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO authorization_memberships "
                "(household_id,user_id,role,status,source_stream_version,source_global_position,"
                "updated_at) VALUES (:household_id,:user_id,'owner','active',2,:position,:now)"
            ),
            {
                "household_id": str(write.result.household_id),
                "user_id": str(write.result.user_id),
                "position": global_position,
                "now": write.recorded_at.isoformat(timespec="microseconds"),
            },
        )

    @staticmethod
    def _insert_operation(connection: Connection, write: BootstrapWrite) -> None:
        result_json = json.dumps(
            {
                "household_id": str(write.result.household_id),
                "user_id": str(write.result.user_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        event_results = json.dumps(
            [
                {"event_id": str(event.event_id), "stream_version": event.stream_version}
                for event in write.events
            ],
            separators=(",", ":"),
        )
        now = write.recorded_at.isoformat(timespec="microseconds")
        expires = (write.recorded_at + timedelta(days=90)).isoformat(timespec="microseconds")
        connection.execute(
            text(
                "INSERT INTO idempotency_operations "
                "(operation_id,household_id,actor_user_id,operation_scope,idempotency_key,"
                "command_hash,status,result_events_json,stored_result_json,"
                "stored_result_schema_version,correlation_id,created_at,completed_at,expires_at) "
                "VALUES (:operation_id,:household_id,:actor_user_id,'household.bootstrap',:key,"
                ":command_hash,'completed',:events,:result,1,:correlation_id,:now,:now,:expires)"
            ),
            {
                "operation_id": str(uuid4()),
                "household_id": str(write.result.household_id),
                "actor_user_id": str(write.result.user_id),
                "key": write.idempotency_key,
                "command_hash": write.command_hash,
                "events": event_results,
                "result": result_json,
                "correlation_id": str(write.correlation_id),
                "now": now,
                "expires": expires,
            },
        )

    @staticmethod
    def _insert_audit(connection: Connection, write: BootstrapWrite) -> None:
        connection.execute(
            text(
                "INSERT INTO security_audit "
                "(audit_id,recorded_at,category,action,outcome,actor_user_id,household_id,"
                "target_type,target_id,correlation_id,details_json) "
                "VALUES (:audit_id,:now,'identity','household.bootstrap','success',:user_id,"
                ":household_id,'household',:household_id,:correlation_id,'{}')"
            ),
            {
                "audit_id": str(uuid4()),
                "now": write.recorded_at.isoformat(timespec="microseconds"),
                "user_id": str(write.result.user_id),
                "household_id": str(write.result.household_id),
                "correlation_id": str(write.correlation_id),
            },
        )
