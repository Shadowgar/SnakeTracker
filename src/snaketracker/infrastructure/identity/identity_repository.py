"""SQLite identity, session, authorization, throttle, and audit adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from snaketracker.application.identity import Credential, Principal, SessionWrite


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class SQLAlchemyIdentityRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def has_users(self) -> bool:
        with self._engine.connect() as connection:
            return bool(connection.execute(text("SELECT EXISTS(SELECT 1 FROM users)")).scalar_one())

    def login_is_blocked(self, key_hash: str, now: datetime) -> bool:
        with self._engine.connect() as connection:
            blocked_until = connection.execute(
                text("SELECT blocked_until FROM login_rate_limits WHERE key_hash=:key"),
                {"key": key_hash},
            ).scalar_one_or_none()
        return blocked_until is not None and str(blocked_until) > _timestamp(now)

    def credential_for(self, email_normalized: str) -> Credential | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT user_id,password_hash,status FROM users "
                        "WHERE email_normalized=:email"
                    ),
                    {"email": email_normalized},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return Credential(UUID(row["user_id"]), row["password_hash"], row["status"])

    def active_household_for(self, user_id: UUID) -> UUID | None:
        with self._engine.connect() as connection:
            household_id = connection.execute(
                text(
                    "SELECT household_id FROM authorization_memberships "
                    "WHERE user_id=:user_id AND status='active' ORDER BY household_id LIMIT 1"
                ),
                {"user_id": str(user_id)},
            ).scalar_one_or_none()
        return UUID(household_id) if household_id else None

    def record_login_failure(
        self,
        key_hash: str,
        *,
        limit: int,
        window: timedelta,
        block_duration: timedelta,
        now: datetime,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT failure_count,window_started_at FROM login_rate_limits "
                        "WHERE key_hash=:key"
                    ),
                    {"key": key_hash},
                )
                .mappings()
                .one_or_none()
            )
            reset = row is None or str(row["window_started_at"]) <= _timestamp(now - window)
            failures = 1 if reset or row is None else int(row["failure_count"]) + 1
            started = (
                now
                if reset or row is None
                else datetime.fromisoformat(str(row["window_started_at"]))
            )
            blocked = now + block_duration if failures >= limit else None
            connection.execute(
                text(
                    "INSERT INTO login_rate_limits "
                    "(key_hash,failure_count,window_started_at,blocked_until,updated_at) "
                    "VALUES (:key,:failures,:started,:blocked,:now) "
                    "ON CONFLICT(key_hash) DO UPDATE SET failure_count=:failures,"
                    "window_started_at=:started,blocked_until=:blocked,updated_at=:now"
                ),
                {
                    "key": key_hash,
                    "failures": failures,
                    "started": _timestamp(started),
                    "blocked": _timestamp(blocked) if blocked else None,
                    "now": _timestamp(now),
                },
            )
            self._audit(
                connection,
                now=now,
                action="login",
                outcome="failure",
                correlation_id=correlation_id,
                client_ip=client_ip,
                user_agent=user_agent,
                details={"reason": "invalid_credentials"},
            )

    def clear_login_failures(self, key_hash: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("DELETE FROM login_rate_limits WHERE key_hash=:key"), {"key": key_hash}
            )

    def create_session(self, write: SessionWrite, *, correlation_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(session_id,user_id,household_id,token_hash,csrf_token_hash,created_at,"
                    "last_seen_at,"
                    "idle_expires_at,absolute_expires_at,client_ip,user_agent_class) VALUES "
                    "(:session_id,:user_id,:household_id,:token_hash,:csrf_hash,:created,:created,"
                    ":idle,:absolute,:client_ip,:user_agent)"
                ),
                {
                    "session_id": str(write.session_id),
                    "user_id": str(write.user_id),
                    "household_id": str(write.household_id),
                    "token_hash": write.token_hash,
                    "csrf_hash": write.csrf_token_hash,
                    "created": _timestamp(write.created_at),
                    "idle": _timestamp(write.idle_expires_at),
                    "absolute": _timestamp(write.absolute_expires_at),
                    "client_ip": write.client_ip,
                    "user_agent": write.user_agent_class,
                },
            )
            self._audit(
                connection,
                now=write.created_at,
                action="login",
                outcome="success",
                correlation_id=correlation_id,
                actor_user_id=write.user_id,
                client_ip=write.client_ip,
                user_agent=write.user_agent_class,
                details={},
            )

    def resolve_session(
        self, token_hash: str, *, now: datetime, idle_timeout: timedelta
    ) -> Principal | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT s.session_id,s.user_id,s.absolute_expires_at,u.display_name,"
                        "m.household_id,m.role,h.name AS household_name "
                        "FROM sessions s JOIN users u ON u.user_id=s.user_id "
                        "JOIN authorization_memberships m ON m.user_id=u.user_id "
                        "AND m.household_id=s.household_id "
                        "JOIN household_summaries h ON h.household_id=s.household_id "
                        "WHERE s.token_hash=:token AND s.revoked_at IS NULL "
                        "AND s.idle_expires_at>:now AND s.absolute_expires_at>:now "
                        "AND u.status='active' AND m.status='active'"
                    ),
                    {"token": token_hash, "now": _timestamp(now)},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            absolute = datetime.fromisoformat(str(row["absolute_expires_at"]))
            idle_expiry = min(now + idle_timeout, absolute)
            connection.execute(
                text(
                    "UPDATE sessions SET last_seen_at=:now,idle_expires_at=:idle "
                    "WHERE session_id=:session_id"
                ),
                {
                    "now": _timestamp(now),
                    "idle": _timestamp(idle_expiry),
                    "session_id": row["session_id"],
                },
            )
            return Principal(
                UUID(row["user_id"]),
                UUID(row["household_id"]),
                row["display_name"],
                row["household_name"],
                row["role"],
                frozenset(),
            )

    def csrf_hash_for(self, token_hash: str, *, now: datetime) -> str | None:
        with self._engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT csrf_token_hash FROM sessions WHERE token_hash=:token "
                    "AND revoked_at IS NULL AND idle_expires_at>:now AND absolute_expires_at>:now"
                ),
                {"token": token_hash, "now": _timestamp(now)},
            ).scalar_one_or_none()
        return str(value) if value is not None else None

    def revoke_session(self, token_hash: str, *, now: datetime, correlation_id: UUID) -> None:
        with self._engine.begin() as connection:
            user_id = connection.execute(
                text("SELECT user_id FROM sessions WHERE token_hash=:token"),
                {"token": token_hash},
            ).scalar_one_or_none()
            connection.execute(
                text(
                    "UPDATE sessions SET revoked_at=:now,revocation_reason='logout' "
                    "WHERE token_hash=:token AND revoked_at IS NULL"
                ),
                {"now": _timestamp(now), "token": token_hash},
            )
            self._audit(
                connection,
                now=now,
                action="logout",
                outcome="success",
                correlation_id=correlation_id,
                actor_user_id=UUID(user_id) if user_id else None,
                details={},
            )

    def record_access_denied(
        self,
        *,
        now: datetime,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        with self._engine.begin() as connection:
            self._audit(
                connection,
                now=now,
                action="protected_request",
                outcome="denied",
                correlation_id=correlation_id,
                client_ip=client_ip,
                user_agent=user_agent,
                details={"reason": "authentication_or_membership_invalid"},
            )

    def revoke_all_sessions(self, *, reason: str, now: datetime, correlation_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE sessions SET revoked_at=:now,revocation_reason=:reason "
                    "WHERE revoked_at IS NULL"
                ),
                {"now": _timestamp(now), "reason": reason},
            )
            self._audit(
                connection,
                now=now,
                action="sessions_invalidated",
                outcome="success",
                correlation_id=correlation_id,
                details={"reason": reason},
            )

    @staticmethod
    def _audit(
        connection: Connection,
        *,
        now: datetime,
        action: str,
        outcome: str,
        correlation_id: UUID,
        details: dict[str, object],
        actor_user_id: UUID | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO security_audit "
                "(audit_id,recorded_at,category,action,outcome,actor_user_id,correlation_id,"
                "client_ip,user_agent_class,details_json) VALUES "
                "(:audit_id,:now,'authentication',:action,:outcome,:actor,:correlation,"
                ":client_ip,:user_agent,:details)"
            ),
            {
                "audit_id": str(uuid4()),
                "now": _timestamp(now),
                "action": action,
                "outcome": outcome,
                "actor": str(actor_user_id) if actor_user_id else None,
                "correlation": str(correlation_id),
                "client_ip": client_ip,
                "user_agent": (user_agent or "")[:64] or None,
                "details": json.dumps(details, sort_keys=True),
            },
        )
