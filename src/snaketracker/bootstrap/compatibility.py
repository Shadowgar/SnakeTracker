"""Read-only startup compatibility evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

CURRENT_MANIFEST_VERSION = 1
CURRENT_RELATIONAL_SCHEMA_VERSION = 1
MINIMUM_RELATIONAL_SCHEMA_VERSION = 0


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
