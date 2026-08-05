"""Identity, session, authorization, and login-throttling use cases."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4


class AuthenticationError(RuntimeError):
    """A generic authentication failure safe to show to a user."""


class LoginBlockedError(AuthenticationError):
    """A login attempt rejected by the durable throttle."""


@dataclass(frozen=True, slots=True)
class Credential:
    user_id: UUID
    password_hash: str
    status: str


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    csrf_token: str
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    household_id: UUID
    display_name: str
    household_name: str
    role: str
    capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class SessionWrite:
    session_id: UUID
    user_id: UUID
    household_id: UUID
    token_hash: str
    csrf_token_hash: str
    created_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    client_ip: str | None
    user_agent_class: str | None


class PasswordVerifyPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class IdentityRepository(Protocol):
    def login_is_blocked(self, key_hash: str, now: datetime) -> bool: ...

    def credential_for(self, email_normalized: str) -> Credential | None: ...

    def active_household_for(self, user_id: UUID) -> UUID | None: ...

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
    ) -> None: ...

    def clear_login_failures(self, key_hash: str) -> None: ...

    def create_session(self, write: SessionWrite, *, correlation_id: UUID) -> None: ...

    def resolve_session(
        self, token_hash: str, *, now: datetime, idle_timeout: timedelta
    ) -> Principal | None: ...

    def csrf_hash_for(self, token_hash: str, *, now: datetime) -> str | None: ...

    def revoke_session(self, token_hash: str, *, now: datetime, correlation_id: UUID) -> None: ...

    def record_access_denied(
        self,
        *,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None: ...


ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset({"household.view", "household.manage", "identity.manage"}),
    "administrator": frozenset({"household.view", "household.manage", "identity.manage"}),
    "caretaker": frozenset({"household.view"}),
    "viewer": frozenset({"household.view"}),
}


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        password_hasher: PasswordVerifyPort,
        *,
        secret: bytes,
        idle_timeout: timedelta,
        absolute_timeout: timedelta,
        rate_limit: int,
        rate_window: timedelta,
        block_duration: timedelta,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("identity secret must be at least 32 bytes")
        self._repository = repository
        self._password_hasher = password_hasher
        self._secret = secret
        self._idle_timeout = idle_timeout
        self._absolute_timeout = absolute_timeout
        self._rate_limit = rate_limit
        self._rate_window = rate_window
        self._block_duration = block_duration
        self._dummy_hash = password_hasher.hash("not-a-real-user-password")

    def login(
        self,
        email: str,
        password: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> IssuedSession:
        current = now or datetime.now(UTC)
        normalized = email.strip().casefold()
        rate_key = self._digest(f"login:{normalized}:{client_ip or '-'}")
        if self._repository.login_is_blocked(rate_key, current):
            raise LoginBlockedError("Too many attempts. Please wait and try again.")
        credential = self._repository.credential_for(normalized)
        candidate_hash = credential.password_hash if credential else self._dummy_hash
        valid = self._password_hasher.verify(candidate_hash, password)
        if not credential or credential.status != "active" or not valid:
            self._repository.record_login_failure(
                rate_key,
                limit=self._rate_limit,
                window=self._rate_window,
                block_duration=self._block_duration,
                now=current,
                correlation_id=correlation_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            raise AuthenticationError("Email or password is incorrect.")
        self._repository.clear_login_failures(rate_key)
        return self._issue_session(
            credential.user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=correlation_id,
            now=current,
        )

    def create_session_for_user(
        self,
        user_id: UUID,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> IssuedSession:
        return self._issue_session(
            user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=correlation_id,
            now=now or datetime.now(UTC),
        )

    def authenticate(self, token: str, *, now: datetime | None = None) -> Principal:
        principal = self._repository.resolve_session(
            self._digest(f"session:{token}"),
            now=now or datetime.now(UTC),
            idle_timeout=self._idle_timeout,
        )
        if principal is None:
            raise AuthenticationError("Your session is no longer valid. Please log in again.")
        return Principal(
            user_id=principal.user_id,
            household_id=principal.household_id,
            display_name=principal.display_name,
            household_name=principal.household_name,
            role=principal.role,
            capabilities=ROLE_CAPABILITIES.get(principal.role, frozenset()),
        )

    def verify_csrf(self, token: str, submitted_token: str) -> bool:
        expected = self._repository.csrf_hash_for(
            self._digest(f"session:{token}"), now=datetime.now(UTC)
        )
        actual = self._digest(f"csrf:{submitted_token}")
        return expected is not None and hmac.compare_digest(expected, actual)

    def logout(self, token: str, *, correlation_id: UUID, now: datetime | None = None) -> None:
        self._repository.revoke_session(
            self._digest(f"session:{token}"),
            now=now or datetime.now(UTC),
            correlation_id=correlation_id,
        )

    def audit_access_denied(
        self,
        *,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self._repository.record_access_denied(
            correlation_id=correlation_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    def rotate_session(
        self,
        token: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> IssuedSession:
        current = now or datetime.now(UTC)
        principal = self.authenticate(token, now=current)
        self.logout(token, correlation_id=correlation_id, now=current)
        return self._issue_session(
            principal.user_id,
            household_id=principal.household_id,
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=correlation_id,
            now=current,
        )

    def _issue_session(
        self,
        user_id: UUID,
        *,
        household_id: UUID | None = None,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime,
    ) -> IssuedSession:
        selected_household = household_id or self._repository.active_household_for(user_id)
        if selected_household is None:
            raise AuthenticationError("No active household membership is available.")
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        absolute_expiry = now + self._absolute_timeout
        self._repository.create_session(
            SessionWrite(
                session_id=uuid4(),
                user_id=user_id,
                household_id=selected_household,
                token_hash=self._digest(f"session:{token}"),
                csrf_token_hash=self._digest(f"csrf:{csrf_token}"),
                created_at=now,
                idle_expires_at=min(now + self._idle_timeout, absolute_expiry),
                absolute_expires_at=absolute_expiry,
                client_ip=client_ip,
                user_agent_class=(user_agent or "")[:64] or None,
            ),
            correlation_id=correlation_id,
        )
        return IssuedSession(token, csrf_token, absolute_expiry)

    def _digest(self, value: str) -> str:
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()
