"""Internal trusted-local adapter for ADR-0040 demo-household provisioning."""

from __future__ import annotations

import os

from snaketracker.application.household_bootstrap import (
    BootstrapResult,
    DemoHouseholdProvisioningCommand,
    DemoHouseholdProvisioningService,
)
from snaketracker.bootstrap.configuration import Settings, load_settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

_PASSWORD_ENVIRONMENT_KEY = "SNAKETRACKER_DEMO_PASSWORD"


def provision_demo_household(settings: Settings, *, password: str) -> BootstrapResult:
    """Provision the reserved household without exposing a browser or public API surface."""
    if settings.runtime_secret is None:
        raise RuntimeError("Trusted local demo provisioning requires the runtime secret.")
    engine = create_sqlite_engine(settings.database_path, require_local_storage=False)
    try:
        service = DemoHouseholdProvisioningService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher(),
            command_hash_secret=settings.runtime_secret.get_secret_value().encode(),
            environment=settings.environment.value,
        )
        return service.provision(DemoHouseholdProvisioningCommand(password=password))
    finally:
        engine.dispose()


def main() -> int:
    password = os.environ.get(_PASSWORD_ENVIRONMENT_KEY)
    if password is None:
        raise SystemExit(f"{_PASSWORD_ENVIRONMENT_KEY} must be provided through the environment")
    result = provision_demo_household(load_settings(), password=password)
    print(f"trusted local demo household ready: household_id={result.household_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
