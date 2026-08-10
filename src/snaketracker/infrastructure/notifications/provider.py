"""Deterministic local notification provider and safe adapter registration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

LOCAL_OPERATION_NAMESPACE = UUID("beaf0a45-5074-5afd-a641-92e1cd248625")


class TransientNotificationError(RuntimeError):
    """Provider rejected work in a way that is safe to retry."""


class PermanentNotificationError(RuntimeError):
    """Provider rejected work permanently."""


@dataclass(frozen=True, slots=True)
class NotificationProviderCapabilities:
    provider_idempotency: bool
    lookup_reconciliation: bool
    bounded_duplicate_tolerance: bool


@dataclass(frozen=True, slots=True)
class ProviderOperation:
    provider_operation_id: str
    provider_idempotency_key: str
    accepted_at: datetime


class NotificationProvider(Protocol):
    capabilities: NotificationProviderCapabilities

    def lookup(self, provider_key: str) -> ProviderOperation | None: ...

    def deliver(
        self, payload: dict[str, object], provider_key: str, *, now: datetime
    ) -> ProviderOperation: ...


class NotificationProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, NotificationProvider] = {}

    def register(self, name: str, provider: NotificationProvider) -> None:
        key = name.strip()
        if not key or key in self._providers:
            raise ValueError("Notification provider name is invalid or already registered.")
        capabilities = provider.capabilities
        if not (
            capabilities.provider_idempotency
            or capabilities.lookup_reconciliation
            or capabilities.bounded_duplicate_tolerance
        ):
            raise ValueError("Notification provider does not control uncertain external effects.")
        self._providers[key] = provider

    def provider(self, name: str) -> NotificationProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise KeyError("Notification provider is not registered.") from error


class LocalQualificationNotificationProvider:
    """Provider-style durable acceptance with no email, SMS, or network side effect."""

    capabilities = NotificationProviderCapabilities(
        provider_idempotency=True,
        lookup_reconciliation=True,
        bounded_duplicate_tolerance=False,
    )

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def lookup(self, provider_key: str) -> ProviderOperation | None:
        with self._engine.connect() as connection:
            row = self._lookup(connection, provider_key)
        return _operation(row) if row is not None else None

    def deliver(
        self, payload: dict[str, object], provider_key: str, *, now: datetime
    ) -> ProviderOperation:
        accepted_at = _utc(now)
        key = _provider_key(provider_key)
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        payload_hash = sha256(canonical).hexdigest()
        operation_id = f"local-{uuid5(LOCAL_OPERATION_NAMESPACE, key)}"
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                existing = self._lookup(connection, key)
                if existing is not None:
                    if existing["payload_hash"] != payload_hash:
                        raise PermanentNotificationError(
                            "Provider idempotency key was reused with a different payload."
                        )
                    connection.rollback()
                    return _operation(existing)
                connection.execute(
                    text(
                        "INSERT INTO local_notification_operations "
                        "(provider_operation_id,provider_idempotency_key,payload_hash,accepted_at) "
                        "VALUES (:operation_id,:provider_key,:payload_hash,:accepted_at)"
                    ),
                    {
                        "operation_id": operation_id,
                        "provider_key": key,
                        "payload_hash": payload_hash,
                        "accepted_at": _timestamp(accepted_at),
                    },
                )
                connection.commit()
                return ProviderOperation(operation_id, key, accepted_at)
            except Exception:
                connection.rollback()
                raise

    def operation_count(self) -> int:
        with self._engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT COUNT(*) FROM local_notification_operations")
                ).scalar_one()
            )

    @staticmethod
    def _lookup(connection: Connection, provider_key: str) -> RowMapping | None:
        return (
            connection.execute(
                text(
                    "SELECT * FROM local_notification_operations "
                    "WHERE provider_idempotency_key=:provider_key"
                ),
                {"provider_key": provider_key},
            )
            .mappings()
            .one_or_none()
        )


def _operation(row: RowMapping) -> ProviderOperation:
    return ProviderOperation(
        provider_operation_id=str(row["provider_operation_id"]),
        provider_idempotency_key=str(row["provider_idempotency_key"]),
        accepted_at=datetime.fromisoformat(str(row["accepted_at"])),
    )


def _provider_key(value: str) -> str:
    key = value.strip()
    if not key or len(key) > 200:
        raise PermanentNotificationError("Provider idempotency key is invalid.")
    return key


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Provider operation time must include a timezone.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
