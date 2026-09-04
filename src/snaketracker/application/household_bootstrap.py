"""Atomic initial identity and household bootstrap application service."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid5

from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum

BOOTSTRAP_NAMESPACE = UUID("ab66c5ca-7d6b-4f8b-bfdd-94437acc3c4a")
DEMO_IDEMPOTENCY_KEY = "trusted-local-carekeeper-owner-review-v2"
DEMO_HOUSEHOLD_ID = str(uuid5(BOOTSTRAP_NAMESPACE, f"household:{DEMO_IDEMPOTENCY_KEY}"))
DEMO_OWNER_USER_ID = str(uuid5(BOOTSTRAP_NAMESPACE, f"user:{DEMO_IDEMPOTENCY_KEY}"))
DEMO_EMAIL = "demo@carekeeper.local"
_DEMO_ALLOWED_ENVIRONMENTS = frozenset({"development", "test", "local-owner-review"})


class BootstrapConflictError(RuntimeError):
    """An idempotency key was reused for a different bootstrap command."""


class AlreadyBootstrappedError(RuntimeError):
    """The one-time initial household bootstrap is no longer available."""


class BootstrapValidationError(ValueError):
    """The submitted bootstrap command failed safe domain validation."""


class AccountRegistrationConflictError(RuntimeError):
    """A production account registration conflicts with existing identity state."""


class DemoProvisioningConflictError(RuntimeError):
    """Reserved demo identity state exists without the matching completed operation."""


class DemoProvisioningEnvironmentError(RuntimeError):
    """Trusted local demo provisioning was requested outside its explicit allow-list."""


@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    household_name: str
    timezone: str
    owner_email: str
    owner_display_name: str
    password: str
    idempotency_key: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class AccountRegistrationCommand:
    collection_name: str
    timezone: str
    email: str
    display_name: str
    password: str
    idempotency_key: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    household_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class BootstrapWrite:
    result: BootstrapResult
    email_normalized: str
    owner_display_name: str
    password_hash: str
    command_hash: str
    correlation_id: UUID
    idempotency_key: str
    events: tuple[DomainEvent, DomainEvent]
    recorded_at: datetime
    operation_scope: str
    audit_action: str


@dataclass(frozen=True, slots=True)
class DemoHouseholdProvisioningCommand:
    password: str


class PasswordHashPort(Protocol):
    def hash(self, password: str) -> str: ...


class HouseholdBootstrapRepository(Protocol):
    def bootstrap(self, write: BootstrapWrite) -> BootstrapResult: ...

    def provision_demo(self, write: BootstrapWrite) -> BootstrapResult: ...

    def register_account(self, write: BootstrapWrite) -> BootstrapResult: ...


class HouseholdBootstrapService:
    def __init__(
        self,
        repository: HouseholdBootstrapRepository,
        password_hasher: PasswordHashPort,
        *,
        command_hash_secret: bytes,
    ) -> None:
        if len(command_hash_secret) < 32:
            raise ValueError("bootstrap command hash secret must be at least 32 bytes")
        self._repository = repository
        self._password_hasher = password_hasher
        self._command_hash_secret = command_hash_secret

    def bootstrap(self, command: BootstrapCommand) -> BootstrapResult:
        write = self._prepare_write(
            command,
            operation_scope="household.bootstrap",
            audit_action="household.bootstrap",
        )
        return self._repository.bootstrap(write)

    def _prepare_write(
        self,
        command: BootstrapCommand,
        *,
        operation_scope: str,
        audit_action: str,
    ) -> BootstrapWrite:
        normalized = _validate(command)
        household_id = uuid5(BOOTSTRAP_NAMESPACE, f"household:{command.idempotency_key}")
        user_id = uuid5(BOOTSTRAP_NAMESPACE, f"user:{command.idempotency_key}")
        recorded_at = datetime.now(UTC)
        return BootstrapWrite(
            result=BootstrapResult(household_id, user_id),
            email_normalized=normalized["owner_email"],
            owner_display_name=normalized["owner_display_name"],
            password_hash=self._password_hasher.hash(command.password),
            command_hash=self._command_hash(normalized),
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            events=_bootstrap_events(command, household_id, user_id, recorded_at),
            recorded_at=recorded_at,
            operation_scope=operation_scope,
            audit_action=audit_action,
        )

    def _command_hash(self, normalized: dict[str, str]) -> str:
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._command_hash_secret, canonical, hashlib.sha256).hexdigest()


class AccountRegistrationService(HouseholdBootstrapService):
    """Create an independent production household and its first owner atomically."""

    def register(self, command: AccountRegistrationCommand) -> BootstrapResult:
        write = self._prepare_write(
            BootstrapCommand(
                household_name=command.collection_name,
                timezone=command.timezone,
                owner_email=command.email,
                owner_display_name=command.display_name,
                password=command.password,
                idempotency_key=command.idempotency_key,
                correlation_id=command.correlation_id,
            ),
            operation_scope="account.register",
            audit_action="account.register",
        )
        return self._repository.register_account(write)


class DemoHouseholdProvisioningService(HouseholdBootstrapService):
    """Provision the one reserved M6 household through a trusted local-only boundary."""

    def __init__(
        self,
        repository: HouseholdBootstrapRepository,
        password_hasher: PasswordHashPort,
        *,
        command_hash_secret: bytes,
        environment: str,
    ) -> None:
        super().__init__(repository, password_hasher, command_hash_secret=command_hash_secret)
        self._environment = environment

    def provision(self, command: DemoHouseholdProvisioningCommand) -> BootstrapResult:
        if self._environment not in _DEMO_ALLOWED_ENVIRONMENTS:
            raise DemoProvisioningEnvironmentError(
                "Trusted local demo provisioning is not permitted in this environment."
            )
        bootstrap_command = BootstrapCommand(
            household_name="Care Keeper Fictional Collection",
            timezone="America/New_York",
            owner_email=DEMO_EMAIL,
            owner_display_name="Demo Keeper",
            password=command.password,
            idempotency_key=DEMO_IDEMPOTENCY_KEY,
            correlation_id=uuid5(BOOTSTRAP_NAMESPACE, "trusted-local-m6-demo-correlation-v1"),
        )
        write = self._prepare_write(
            bootstrap_command,
            operation_scope="household.demo_provision",
            audit_action="household.demo_provision",
        )
        return self._repository.provision_demo(write)


def _validate(command: BootstrapCommand) -> dict[str, str]:
    name = command.household_name.strip()
    display_name = command.owner_display_name.strip()
    email = command.owner_email.strip().casefold()
    if not name or len(name) > 120:
        raise BootstrapValidationError("household name is required")
    if not display_name or len(display_name) > 120:
        raise BootstrapValidationError("owner display name is required")
    if "@" not in email or len(email) > 320:
        raise BootstrapValidationError("a valid owner email is required")
    if len(command.password) < 12 or len(command.password) > 1024:
        raise BootstrapValidationError("password must be between 12 and 1024 characters")
    if not command.timezone or len(command.timezone) > 64:
        raise BootstrapValidationError("timezone is required")
    if len(command.idempotency_key) < 16 or len(command.idempotency_key) > 128:
        raise BootstrapValidationError("idempotency key is invalid")
    return {
        "household_name": name,
        "timezone": command.timezone,
        "owner_email": email,
        "owner_display_name": display_name,
        "password_fingerprint": hashlib.sha256(command.password.encode()).hexdigest(),
    }


def _bootstrap_events(
    command: BootstrapCommand,
    household_id: UUID,
    user_id: UUID,
    recorded_at: datetime,
) -> tuple[DomainEvent, DomainEvent]:
    created_id = uuid5(BOOTSTRAP_NAMESPACE, f"{command.idempotency_key}:event:1")
    owner_id = uuid5(BOOTSTRAP_NAMESPACE, f"{command.idempotency_key}:event:2")
    created = DomainEvent(
        event_id=created_id,
        household_id=household_id,
        stream_type="household",
        stream_id=household_id,
        stream_version=1,
        event_type="household.created",
        schema_version=1,
        occurred_at=recorded_at,
        recorded_at=recorded_at,
        actor_user_id=user_id,
        correlation_id=command.correlation_id,
        causation_id=None,
        idempotency_key=command.idempotency_key,
        subjects=(EventSubject("household", household_id, "primary", 0),),
        title="Household created",
        description=None,
        payload=HouseholdCreatedV1(command.household_name.strip(), command.timezone),
        metadata={},
        notes=None,
        checksum="",
    )
    created = created.with_checksum(event_checksum(created))
    owner_added = DomainEvent(
        event_id=owner_id,
        household_id=household_id,
        stream_type="household",
        stream_id=household_id,
        stream_version=2,
        event_type="household.owner_added",
        schema_version=1,
        occurred_at=recorded_at,
        recorded_at=recorded_at,
        actor_user_id=user_id,
        correlation_id=command.correlation_id,
        causation_id=created_id,
        idempotency_key=command.idempotency_key,
        subjects=(
            EventSubject("household", household_id, "primary", 0),
            EventSubject("user", user_id, "related", 1),
        ),
        title="Initial owner added",
        description=None,
        payload=HouseholdOwnerAddedV1(user_id, "owner"),
        metadata={},
        notes=None,
        checksum="",
    )
    owner_added = owner_added.with_checksum(event_checksum(owner_added))
    return created, owner_added
