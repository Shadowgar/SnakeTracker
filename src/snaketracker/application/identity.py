"""Identity, session, authorization, and login-throttling use cases."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import quote
from uuid import UUID, uuid4


class AuthenticationError(RuntimeError):
    """A generic authentication failure safe to show to a user."""


class LoginBlockedError(AuthenticationError):
    """A login attempt rejected by the durable throttle."""


class PasswordResetValidationError(AuthenticationError):
    """A password-reset submission that violates the public password policy."""


class InvalidPasswordResetError(AuthenticationError):
    """An invalid, expired, superseded, or consumed reset credential."""


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
    household_timezone: str
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


@dataclass(frozen=True, slots=True)
class PasswordResetWrite:
    reset_id: UUID
    token_hash: str
    requested_at: datetime
    expires_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class PasswordResetRecipient:
    reset_id: UUID
    user_id: UUID
    email_normalized: str


@dataclass(frozen=True, slots=True)
class PasswordResetMessage:
    message_id: UUID
    recipient_email: str
    reset_url: str
    expires_at: datetime


class PasswordVerifyPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class PasswordResetDeliveryPort(Protocol):
    def deliver(self, message: PasswordResetMessage) -> None: ...


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

    def record_registration_failure(
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

    def create_session(self, write: SessionWrite, *, correlation_id: UUID) -> None: ...

    def resolve_session(
        self, token_hash: str, *, now: datetime, idle_timeout: timedelta
    ) -> Principal | None: ...

    def csrf_hash_for(self, token_hash: str, *, now: datetime) -> str | None: ...

    def revoke_session(self, token_hash: str, *, now: datetime, correlation_id: UUID) -> None: ...

    def record_access_denied(
        self,
        *,
        now: datetime,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None: ...

    def revoke_all_sessions(self, *, reason: str, now: datetime, correlation_id: UUID) -> None: ...

    def request_password_reset(
        self,
        email_normalized: str,
        write: PasswordResetWrite,
        *,
        rate_key: str | None,
        limit: int,
        window: timedelta,
        block_duration: timedelta,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> PasswordResetRecipient | None: ...

    def invalidate_password_reset(
        self,
        reset_id: UUID,
        *,
        now: datetime,
        correlation_id: UUID,
        reason: str,
    ) -> None: ...

    def complete_password_reset(
        self,
        token_hash: str,
        password_hash: str,
        *,
        now: datetime,
        correlation_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> bool: ...


ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "household.view",
            "household.manage",
            "identity.manage",
            "inventory.view",
            "inventory.manage",
            "expense.view",
            "expense.manage",
            "reminder.view",
            "reminder.manage",
            "operations.view",
            "operations.manage",
        }
    ),
    "administrator": frozenset(
        {
            "household.view",
            "household.manage",
            "identity.manage",
            "inventory.view",
            "inventory.manage",
            "expense.view",
            "expense.manage",
            "reminder.view",
            "reminder.manage",
            "operations.view",
            "operations.manage",
        }
    ),
    "caretaker": frozenset(
        {"household.view", "inventory.view", "inventory.manage", "reminder.view"}
    ),
    "viewer": frozenset({"household.view", "inventory.view", "reminder.view"}),
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
        password_reset_delivery: PasswordResetDeliveryPort | None = None,
        external_origin: str | None = None,
        password_reset_ttl: timedelta = timedelta(minutes=45),
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
        self._password_reset_delivery = password_reset_delivery
        self._external_origin = external_origin.rstrip("/") if external_origin else None
        self._password_reset_ttl = password_reset_ttl
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

    def registration_is_blocked(
        self,
        email: str,
        *,
        client_ip: str | None,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        return self._repository.login_is_blocked(
            self._registration_rate_key(email, client_ip), current
        )

    def record_registration_failure(
        self,
        email: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> None:
        self._repository.record_registration_failure(
            self._registration_rate_key(email, client_ip),
            limit=self._rate_limit,
            window=self._rate_window,
            block_duration=self._block_duration,
            now=now or datetime.now(UTC),
            correlation_id=correlation_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    def clear_registration_failures(self, email: str, *, client_ip: str | None) -> None:
        self._repository.clear_login_failures(self._registration_rate_key(email, client_ip))

    def request_password_reset(
        self,
        email: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> None:
        """Request reset delivery without exposing account or delivery state."""
        current = now or datetime.now(UTC)
        token, recipient = self._create_password_reset(
            email,
            source="self_service",
            rate_key=self._password_reset_rate_key(email, client_ip),
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=correlation_id,
            now=current,
        )
        if recipient is None:
            return
        if self._password_reset_delivery is None or self._external_origin is None:
            self._repository.invalidate_password_reset(
                recipient.reset_id,
                now=current,
                correlation_id=correlation_id,
                reason="delivery_unavailable",
            )
            return
        try:
            self._password_reset_delivery.deliver(
                PasswordResetMessage(
                    message_id=uuid4(),
                    recipient_email=recipient.email_normalized,
                    reset_url=self._reset_url(token),
                    expires_at=current + self._password_reset_ttl,
                )
            )
        except Exception:
            self._repository.invalidate_password_reset(
                recipient.reset_id,
                now=current,
                correlation_id=correlation_id,
                reason="delivery_failed",
            )

    def initiate_operator_password_reset(
        self,
        email: str,
        *,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> str | None:
        """Create a local-operator one-time link without accepting a plaintext password."""
        if self._external_origin is None:
            raise RuntimeError("Operator password recovery requires a configured external origin.")
        current = now or datetime.now(UTC)
        token, recipient = self._create_password_reset(
            email,
            source="operator",
            rate_key=None,
            client_ip=None,
            user_agent="local-operator",
            correlation_id=correlation_id,
            now=current,
        )
        return self._reset_url(token) if recipient is not None else None

    def complete_password_reset(
        self,
        token: str,
        password: str,
        confirmation: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> None:
        if password != confirmation:
            raise PasswordResetValidationError("Passwords do not match.")
        if len(password) < 12 or len(password) > 1024:
            raise PasswordResetValidationError("Password must be between 12 and 1024 characters.")
        current = now or datetime.now(UTC)
        password_hash = self._password_hasher.hash(password)
        if re.fullmatch(r"[A-Za-z0-9_-]{64,128}", token) is None or not (
            self._repository.complete_password_reset(
                self._digest(f"password-reset:{token}"),
                password_hash,
                now=current,
                correlation_id=correlation_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )
        ):
            raise InvalidPasswordResetError(
                "This reset link is invalid or has expired. Request a new one."
            )

    def _create_password_reset(
        self,
        email: str,
        *,
        source: str,
        rate_key: str | None,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        now: datetime,
    ) -> tuple[str, PasswordResetRecipient | None]:
        token = secrets.token_urlsafe(48)
        recipient = self._repository.request_password_reset(
            email.strip().casefold(),
            PasswordResetWrite(
                reset_id=uuid4(),
                token_hash=self._digest(f"password-reset:{token}"),
                requested_at=now,
                expires_at=now + self._password_reset_ttl,
                source=source,
            ),
            rate_key=rate_key,
            limit=self._rate_limit,
            window=self._rate_window,
            block_duration=self._block_duration,
            correlation_id=correlation_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return token, recipient

    def _reset_url(self, token: str) -> str:
        if self._external_origin is None:
            raise RuntimeError("Password recovery requires a configured external origin.")
        return f"{self._external_origin}/reset-password#token={quote(token, safe='')}"

    def _password_reset_rate_key(self, email: str, client_ip: str | None) -> str:
        return self._digest(f"password-reset:{email.strip().casefold()}:{client_ip or '-'}")

    def _registration_rate_key(self, email: str, client_ip: str | None) -> str:
        return self._digest(f"registration:{email.strip().casefold()}:{client_ip or '-'}")

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
            household_timezone=principal.household_timezone,
            role=principal.role,
            capabilities=ROLE_CAPABILITIES.get(principal.role, frozenset()),
        )

    def verify_csrf(self, token: str, submitted_token: str, *, now: datetime | None = None) -> bool:
        expected = self._repository.csrf_hash_for(
            self._digest(f"session:{token}"), now=now or datetime.now(UTC)
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
        now: datetime | None = None,
    ) -> None:
        self._repository.record_access_denied(
            now=now or datetime.now(UTC),
            correlation_id=correlation_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    def invalidate_sessions_after_restoration(
        self, *, correlation_id: UUID, now: datetime | None = None
    ) -> None:
        self._repository.revoke_all_sessions(
            reason="restoration",
            now=now or datetime.now(UTC),
            correlation_id=correlation_id,
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
