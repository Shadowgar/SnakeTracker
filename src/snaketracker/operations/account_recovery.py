"""Trusted local operator password-recovery command."""

from __future__ import annotations

import argparse
from datetime import timedelta
from uuid import uuid4

from snaketracker.application.identity import IdentityService
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher


def initiate_operator_recovery(settings: Settings, *, email: str) -> str | None:
    """Create an audited one-time reset URL without accepting a password."""
    if settings.runtime_secret is None:
        raise RuntimeError("Operator password recovery requires the runtime secret.")
    if settings.external_origin is None:
        raise RuntimeError("Operator password recovery requires the configured external origin.")
    engine = create_sqlite_engine(
        settings.database_path,
        require_local_storage=settings.environment is Environment.PRODUCTION,
    )
    try:
        service = IdentityService(
            SQLAlchemyIdentityRepository(engine),
            Argon2PasswordHasher(),
            secret=settings.runtime_secret.get_secret_value().encode(),
            idle_timeout=timedelta(minutes=30),
            absolute_timeout=timedelta(hours=12),
            rate_limit=5,
            rate_window=timedelta(minutes=15),
            block_duration=timedelta(minutes=15),
            external_origin=str(settings.external_origin).rstrip("/"),
        )
        return service.initiate_operator_password_reset(email, correlation_id=uuid4())
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="carekeeper account password-reset",
        description="Create a one-time password-reset URL for a trusted local operator.",
    )
    parser.add_argument("email", help="Account email address")
    arguments = parser.parse_args()
    reset_url = initiate_operator_recovery(load_settings(), email=arguments.email)
    if reset_url is None:
        print("No reset URL was generated.")
        return 0
    print("One-time password reset URL (do not store or share it):")
    print(reset_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
