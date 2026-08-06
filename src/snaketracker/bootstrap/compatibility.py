"""Read-only startup compatibility evaluation."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from snaketracker.platform.events.registry import (
    UnknownEventContractError,
    production_event_registry,
)

CURRENT_MANIFEST_VERSION = 1
CURRENT_RELATIONAL_SCHEMA_VERSION = 4
MINIMUM_RELATIONAL_SCHEMA_VERSION = 0
MINIMUM_SQLITE_VERSION = (3, 35, 0)


class CompatibilityMode(StrEnum):
    """Startup modes selected before mutable database work begins."""

    NORMAL = "normal"
    MIGRATION_REQUIRED = "migration_required"
    BOOTSTRAP_ALLOWED = "bootstrap_allowed"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Safe compatibility result exposed to startup and readiness logic."""

    mode: CompatibilityMode
    reason_code: str
    public_detail: str

    @property
    def normal_readiness(self) -> bool:
        """Return whether normal application traffic may be accepted."""
        return self.mode is CompatibilityMode.NORMAL


def _report(mode: CompatibilityMode, reason_code: str, detail: str) -> CompatibilityReport:
    return CompatibilityReport(mode=mode, reason_code=reason_code, public_detail=detail)


def evaluate_compatibility(
    metadata: Mapping[str, object] | None, *, database_is_empty: bool
) -> CompatibilityReport:
    """Evaluate stored metadata conservatively without mutating it."""
    if metadata is None:
        if database_is_empty:
            return _report(
                CompatibilityMode.BOOTSTRAP_ALLOWED,
                "empty_database",
                "The database is ready for initial migration.",
            )
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_metadata_missing",
            "Stored data cannot be opened safely.",
        )

    manifest = metadata.get("manifest_version")
    schema = metadata.get("relational_schema_version")
    if type(manifest) is not int or type(schema) is not int:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_metadata_invalid",
            "Stored compatibility metadata is invalid.",
        )
    if manifest != CURRENT_MANIFEST_VERSION:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_manifest_unsupported",
            "Stored data requires a compatible application release.",
        )
    if schema > CURRENT_RELATIONAL_SCHEMA_VERSION:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "relational_schema_too_new",
            "Stored data requires a newer compatible application.",
        )
    if schema < MINIMUM_RELATIONAL_SCHEMA_VERSION:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "relational_schema_too_old",
            "Stored data requires a supported migration path.",
        )
    if schema < CURRENT_RELATIONAL_SCHEMA_VERSION:
        return _report(
            CompatibilityMode.MIGRATION_REQUIRED,
            "relational_schema_upgrade_required",
            "A database migration is required before startup.",
        )
    return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")


def inspect_database_compatibility(engine: Engine) -> CompatibilityReport:
    try:
        with engine.connect() as connection:
            tables = set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).scalars()
            )
            if not tables:
                return evaluate_compatibility(None, database_is_empty=True)
            if "alembic_version" not in tables:
                return evaluate_compatibility(None, database_is_empty=False)
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
    except SQLAlchemyError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_inspection_failed",
            "Stored data could not be inspected safely.",
        )
    if revision == "0004_event_platform":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 4},
            database_is_empty=False,
        )
    if revision == "0003_phase2_review_hardening":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 3},
            database_is_empty=False,
        )
    if revision == "0002_identity_household":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 2},
            database_is_empty=False,
        )
    if revision == "0001_phase1_baseline":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 1},
            database_is_empty=False,
        )
    return _report(
        CompatibilityMode.RECOVERY_REQUIRED,
        "relational_schema_unknown",
        "Stored data requires a compatible application release.",
    )


def evaluate_runtime_compatibility(
    sqlite_version: str, compile_options: Collection[str]
) -> CompatibilityReport:
    """Validate the minimum SQLite runtime required by the Phase 1 release."""
    try:
        version = tuple(int(part) for part in sqlite_version.split("."))
    except ValueError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "sqlite_version_invalid",
            "The database runtime is not compatible with this release.",
        )
    if len(version) < 3 or version[:3] < MINIMUM_SQLITE_VERSION:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "sqlite_version_unsupported",
            "The database runtime is not compatible with this release.",
        )
    if "ENABLE_FTS5" not in compile_options:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "sqlite_fts5_unavailable",
            "The database runtime is missing a required capability.",
        )
    return _report(CompatibilityMode.NORMAL, "runtime_compatible", "The runtime is ready.")


def inspect_runtime_compatibility(engine: Engine) -> CompatibilityReport:
    try:
        with engine.connect() as connection:
            sqlite_version = str(connection.exec_driver_sql("SELECT sqlite_version()").scalar_one())
            compile_options = {
                str(option)
                for option in connection.exec_driver_sql("PRAGMA compile_options").scalars()
            }
    except SQLAlchemyError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "runtime_inspection_failed",
            "The database runtime could not be inspected safely.",
        )
    return evaluate_runtime_compatibility(sqlite_version, compile_options)


def inspect_event_contracts(engine: Engine) -> CompatibilityReport:
    """Reject normal startup when any persisted event contract is unknown."""
    try:
        with engine.connect() as connection:
            contracts = connection.exec_driver_sql(
                "SELECT DISTINCT event_type, schema_version FROM domain_events "
            ).all()
        for event_type, schema_version in contracts:
            production_event_registry.payload_type(str(event_type), int(schema_version))
    except UnknownEventContractError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "event_contract_unknown",
            "Stored event history requires a compatible application release.",
        )
    except (SQLAlchemyError, TypeError, ValueError):
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "event_contract_inspection_failed",
            "Stored event history could not be inspected safely.",
        )
    return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")


inspect_household_event_contracts = inspect_event_contracts


def inspect_startup_compatibility(engine: Engine) -> CompatibilityReport:
    """Require both the release runtime and stored schema to be compatible."""
    runtime = inspect_runtime_compatibility(engine)
    if not runtime.normal_readiness:
        return runtime
    database = inspect_database_compatibility(engine)
    if not database.normal_readiness:
        return database
    return inspect_event_contracts(engine)
