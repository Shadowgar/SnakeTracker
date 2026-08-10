"""Typed runtime configuration and secret-file resolution."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import HttpUrl, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Validated settings composed at process startup."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        hide_input_in_errors=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    database_path: Path = Path("data/snaketracker.sqlite3")
    attachment_storage_path: Path | None = None
    backup_storage_path: Path | None = None
    external_origin: HttpUrl | None = None
    runtime_secret: SecretStr | None = None
    backup_encryption_key: SecretStr | None = None
    backup_encryption_key_id: str = "local-development-v1"
    log_level: str = "INFO"
    session_cookie_secure: bool = True

    @field_validator("external_origin")
    @classmethod
    def require_secure_production_origin(
        cls, value: HttpUrl | None, info: ValidationInfo
    ) -> HttpUrl | None:
        if info.data.get("environment") is Environment.PRODUCTION and (
            value is None or value.scheme != "https"
        ):
            raise ValueError("production external origin must use HTTPS")
        return value

    @field_validator("runtime_secret")
    @classmethod
    def require_production_secret(
        cls, value: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if info.data.get("environment") is Environment.PRODUCTION and value is None:
            raise ValueError("production runtime secret is required")
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("runtime secret must contain at least 32 characters")
        return value

    @field_validator("backup_encryption_key")
    @classmethod
    def require_hex_backup_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        try:
            decoded = bytes.fromhex(secret)
        except ValueError as error:
            raise ValueError("backup encryption key must be hexadecimal") from error
        if len(decoded) != 32:
            raise ValueError("backup encryption key must encode exactly 32 bytes")
        return value

    @field_validator("backup_encryption_key_id")
    @classmethod
    def require_safe_backup_key_id(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value) is None:
            raise ValueError("backup encryption key identifier is invalid")
        return value

    @model_validator(mode="after")
    def require_absolute_production_storage_paths(self) -> Self:
        if self.environment is Environment.PRODUCTION and not self.database_path.is_absolute():
            raise ValueError("production database path must be absolute")
        if (
            self.environment is Environment.PRODUCTION
            and self.attachment_storage_path is not None
            and not self.attachment_storage_path.is_absolute()
        ):
            raise ValueError("production attachment storage path must be absolute")
        if (
            self.environment is Environment.PRODUCTION
            and self.backup_storage_path is not None
            and not self.backup_storage_path.is_absolute()
        ):
            raise ValueError("production backup storage path must be absolute")
        return self


def _resolve_secret(environ: Mapping[str, str], name: str) -> str | None:
    direct = environ.get(name)
    file_name = f"{name}_FILE"
    secret_file = environ.get(file_name)
    if direct is not None and secret_file is not None:
        raise ValueError(f"set either {name} or {file_name}, not both")
    if secret_file is None:
        return direct
    try:
        value = Path(secret_file).read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as error:
        raise ValueError(f"cannot read secret file for {file_name}") from error
    if not value:
        raise ValueError(f"secret file for {file_name} is empty")
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from an explicit mapping or the process environment."""
    source = os.environ if environ is None else environ
    values: dict[str, object] = {}
    keys = {
        "SNAKETRACKER_ENVIRONMENT": "environment",
        "SNAKETRACKER_DATABASE_PATH": "database_path",
        "SNAKETRACKER_ATTACHMENT_STORAGE_PATH": "attachment_storage_path",
        "SNAKETRACKER_BACKUP_STORAGE_PATH": "backup_storage_path",
        "SNAKETRACKER_BACKUP_ENCRYPTION_KEY_ID": "backup_encryption_key_id",
        "SNAKETRACKER_EXTERNAL_ORIGIN": "external_origin",
        "SNAKETRACKER_LOG_LEVEL": "log_level",
        "SNAKETRACKER_SESSION_COOKIE_SECURE": "session_cookie_secure",
    }
    for environment_key, field_name in keys.items():
        if environment_key in source:
            values[field_name] = source[environment_key]
    secret = _resolve_secret(source, "SNAKETRACKER_RUNTIME_SECRET")
    if secret is not None:
        values["runtime_secret"] = secret
    backup_key = _resolve_secret(source, "SNAKETRACKER_BACKUP_ENCRYPTION_KEY")
    if backup_key is not None:
        values["backup_encryption_key"] = backup_key
    return Settings.model_validate(values)
