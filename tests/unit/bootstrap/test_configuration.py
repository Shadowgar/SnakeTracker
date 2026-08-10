from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from snaketracker.bootstrap.configuration import Environment, load_settings


def test_development_settings_have_safe_local_defaults(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "development",
            "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "snaketracker.sqlite3"),
        }
    )

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.database_path == tmp_path / "snaketracker.sqlite3"
    assert settings.external_origin is None
    assert settings.session_cookie_secure is True


def test_local_docker_can_explicitly_disable_secure_cookie() -> None:
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "development",
            "SNAKETRACKER_SESSION_COOKIE_SECURE": "false",
        }
    )

    assert settings.session_cookie_secure is False


def test_production_requires_https_origin_and_runtime_secret(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as error:
        load_settings(
            {
                "SNAKETRACKER_ENVIRONMENT": "production",
                "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "snaketracker.sqlite3"),
                "SNAKETRACKER_EXTERNAL_ORIGIN": "http://snaketracker.example",
            }
        )

    messages = {item["msg"] for item in error.value.errors()}
    assert "Value error, production external origin must use HTTPS" in messages
    assert "Value error, production runtime secret is required" in messages


def test_secret_file_is_read_without_exposing_value_in_repr(tmp_path: Path) -> None:
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_text("a" * 32 + "\n")

    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "production",
            "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "snaketracker.sqlite3"),
            "SNAKETRACKER_EXTERNAL_ORIGIN": "https://snaketracker.example",
            "SNAKETRACKER_RUNTIME_SECRET_FILE": str(secret_file),
        }
    )

    assert settings.runtime_secret is not None
    assert settings.runtime_secret.get_secret_value() == "a" * 32
    assert "a" * 32 not in repr(settings)


def test_backup_key_and_storage_paths_are_loaded_without_exposing_key(tmp_path: Path) -> None:
    key_file = tmp_path / "backup-key"
    key_file.write_text("ab" * 32 + "\n")

    settings = load_settings(
        {
            "SNAKETRACKER_BACKUP_STORAGE_PATH": str(tmp_path / "backups"),
            "SNAKETRACKER_BACKUP_ENCRYPTION_KEY_FILE": str(key_file),
            "SNAKETRACKER_BACKUP_ENCRYPTION_KEY_ID": "operator-key-2026-08",
        }
    )

    assert settings.backup_storage_path == tmp_path / "backups"
    assert settings.backup_encryption_key is not None
    assert settings.backup_encryption_key.get_secret_value() == "ab" * 32
    assert settings.backup_encryption_key_id == "operator-key-2026-08"
    assert "ab" * 32 not in repr(settings)


@pytest.mark.parametrize(
    ("environment_key", "value", "message"),
    (
        ("SNAKETRACKER_BACKUP_ENCRYPTION_KEY", "not-hex", "must be hexadecimal"),
        ("SNAKETRACKER_BACKUP_ENCRYPTION_KEY", "ab" * 8, "exactly 32 bytes"),
        ("SNAKETRACKER_BACKUP_ENCRYPTION_KEY_ID", "unsafe/key", "identifier is invalid"),
    ),
)
def test_backup_key_configuration_rejects_unsafe_values(
    environment_key: str, value: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        load_settings({environment_key: value})


@pytest.mark.parametrize(
    "storage_key",
    (
        "SNAKETRACKER_ATTACHMENT_STORAGE_PATH",
        "SNAKETRACKER_BACKUP_STORAGE_PATH",
    ),
)
def test_production_auxiliary_storage_paths_must_be_absolute(storage_key: str) -> None:
    with pytest.raises(ValidationError, match="storage path must be absolute"):
        load_settings(
            {
                "SNAKETRACKER_ENVIRONMENT": "production",
                "SNAKETRACKER_DATABASE_PATH": "/srv/snaketracker/snaketracker.sqlite3",
                "SNAKETRACKER_EXTERNAL_ORIGIN": "https://snaketracker.example",
                "SNAKETRACKER_RUNTIME_SECRET": "a" * 32,
                storage_key: "relative-storage",
            }
        )


def test_direct_and_file_secret_values_are_ambiguous(tmp_path: Path) -> None:
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_text("b" * 32)

    with pytest.raises(ValueError, match=r"set either .* or .*_FILE"):
        load_settings(
            {
                "SNAKETRACKER_RUNTIME_SECRET": "a" * 32,
                "SNAKETRACKER_RUNTIME_SECRET_FILE": str(secret_file),
            }
        )


def test_unreadable_secret_file_fails_without_secret_content(tmp_path: Path) -> None:
    missing = tmp_path / "missing-secret"

    with pytest.raises(ValueError, match="cannot read secret file") as error:
        load_settings({"SNAKETRACKER_RUNTIME_SECRET_FILE": str(missing)})

    assert str(missing) not in str(error.value)


def test_short_runtime_secret_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        load_settings(
            {
                "SNAKETRACKER_ENVIRONMENT": "production",
                "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "snaketracker.sqlite3"),
                "SNAKETRACKER_EXTERNAL_ORIGIN": "https://snaketracker.example",
                "SNAKETRACKER_RUNTIME_SECRET": "too-short",
            }
        )


def test_empty_secret_file_is_rejected(tmp_path: Path) -> None:
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_text("\n")

    with pytest.raises(ValueError, match=r"secret file .* is empty"):
        load_settings({"SNAKETRACKER_RUNTIME_SECRET_FILE": str(secret_file)})


def test_production_database_path_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="database path must be absolute"):
        load_settings(
            {
                "SNAKETRACKER_ENVIRONMENT": "production",
                "SNAKETRACKER_DATABASE_PATH": "data/snaketracker.sqlite3",
                "SNAKETRACKER_EXTERNAL_ORIGIN": "https://snaketracker.example",
                "SNAKETRACKER_RUNTIME_SECRET": "a" * 32,
            }
        )


def test_process_environment_is_used_when_mapping_is_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SNAKETRACKER_ENVIRONMENT", "test")
    monkeypatch.setenv("SNAKETRACKER_DATABASE_PATH", str(tmp_path / "from-process.sqlite3"))

    settings = load_settings()

    assert settings.environment is Environment.TEST
    assert settings.database_path == tmp_path / "from-process.sqlite3"


@pytest.mark.parametrize(
    "environment",
    [
        {
            "SNAKETRACKER_ENVIRONMENT": "production",
            "SNAKETRACKER_DATABASE_PATH": "/srv/snaketracker.sqlite3",
            "SNAKETRACKER_EXTERNAL_ORIGIN": "https://example.test",
            "SNAKETRACKER_RUNTIME_SECRET": "short-sensitive-value",
        },
        {
            "SNAKETRACKER_ENVIRONMENT": "production",
            "SNAKETRACKER_DATABASE_PATH": "relative.sqlite3",
            "SNAKETRACKER_EXTERNAL_ORIGIN": "https://example.test",
            "SNAKETRACKER_RUNTIME_SECRET": "valid-but-sensitive-value-that-is-long-enough",
        },
    ],
)
def test_validation_errors_never_include_secret_input(
    environment: dict[str, str],
) -> None:
    with pytest.raises(ValueError) as raised:
        load_settings(environment)

    message = str(raised.value)
    assert environment["SNAKETRACKER_RUNTIME_SECRET"] not in message
    assert "input_value=" not in message
