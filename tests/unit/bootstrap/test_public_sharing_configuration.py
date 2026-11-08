"""Public routes cannot be enabled accidentally or before production qualification."""

import pytest
from pydantic import ValidationError

from snaketracker.bootstrap.configuration import load_settings


def test_public_delivery_defaults_off_and_can_be_exercised_in_isolation():
    assert load_settings({}).public_sharing_enabled is False
    assert (
        load_settings(
            {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_PUBLIC_SHARING_ENABLED": "true"}
        ).public_sharing_enabled
        is True
    )


def test_production_public_delivery_remains_a_release_gate():
    with pytest.raises(ValidationError, match="public release qualification"):
        load_settings(
            {
                "SNAKETRACKER_ENVIRONMENT": "production",
                "SNAKETRACKER_DATABASE_PATH": "/fictional/acceptance.sqlite3",
                "SNAKETRACKER_EXTERNAL_ORIGIN": "https://example.test",
                "SNAKETRACKER_RUNTIME_SECRET": "fixture-only-secret-32-characters-long",
                "SNAKETRACKER_PUBLIC_SHARING_ENABLED": "true",
            }
        )
