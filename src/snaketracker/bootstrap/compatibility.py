"""Read-only startup compatibility evaluation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from snaketracker.domains.animals.capabilities import (
    AnimalCapabilityRegistry,
    UnknownCapabilityProfileError,
    animal_capability_registry,
)
from snaketracker.platform.events.registry import (
    UnknownEventContractError,
    production_event_registry,
)
from snaketracker.platform.projections.definitions import (
    ProjectionRegistry,
    production_projection_registry,
)

CURRENT_MANIFEST_VERSION = 1
CURRENT_RELATIONAL_SCHEMA_VERSION = 24
MINIMUM_RELATIONAL_SCHEMA_VERSION = 0
MINIMUM_SQLITE_VERSION = (3, 35, 0)


def supported_profile_release_manifest(
    profiles: AnimalCapabilityRegistry = animal_capability_registry,
    projections: ProjectionRegistry = production_projection_registry,
) -> Mapping[str, object]:
    """Trusted release metadata; never stored as a second source of Animal identity."""
    readable = profiles.readable_identities
    eligible = tuple(
        identity for identity in readable if profiles.require(identity).registration_eligible
    )
    requirements = {
        identity: profiles.require(identity).required_event_contracts for identity in readable
    }
    for contracts in requirements.values():
        for event_type, version in contracts:
            production_event_registry.registration(event_type, version)
    writes = {
        identity: (
            "animal.registered",
            profiles.require_registration(identity).registration_contract_version,
        )
        for identity in eligible
    }
    for event_type, version in writes.values():
        production_event_registry.registration(event_type, version)
    return MappingProxyType(
        {
            "readable_profiles": readable,
            "registration_eligible_profiles": eligible,
            "workflow_defaults": MappingProxyType(
                {
                    group.identity: profiles.registration_profile(group.identity).identity
                    for group in profiles.registration_groups
                }
            ),
            "registration_writes": MappingProxyType(writes),
            "profile_event_requirements": MappingProxyType(requirements),
            "required_identity_contracts": production_event_registry.required_identity_contracts,
            "readable_event_contracts": production_event_registry.identities,
            "projection_requirements": tuple(
                (definition.name, definition.schema_version, definition.handler_version)
                for group in projections.group_names
                for definition in projections.rebuild_group(group)
            ),
            "relational_schema_version": CURRENT_RELATIONAL_SCHEMA_VERSION,
            "backup_manifest_version": 1,
        }
    )


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
    operator_detail: str | None = None

    @property
    def normal_readiness(self) -> bool:
        """Return whether normal application traffic may be accepted."""
        return self.mode is CompatibilityMode.NORMAL


def _report(
    mode: CompatibilityMode,
    reason_code: str,
    detail: str,
    operator_detail: str | None = None,
) -> CompatibilityReport:
    return CompatibilityReport(
        mode=mode, reason_code=reason_code, public_detail=detail, operator_detail=operator_detail
    )


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


def inspect_database_compatibility(engine: Engine | Connection) -> CompatibilityReport:
    try:
        with engine.connect() if isinstance(engine, Engine) else nullcontext(engine) as connection:
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
    if revision == "0024_local_taxonomy":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 24},
            database_is_empty=False,
        )
    if revision == "0023_sourced_care_guides":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 23},
            database_is_empty=False,
        )
    if revision == "0022_reference_image_provenance":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 22},
            database_is_empty=False,
        )
    if revision == "0021_reference_images":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 21},
            database_is_empty=False,
        )
    if revision == "0020_enclosure_plants":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 20},
            database_is_empty=False,
        )
    if revision == "0019_universal_species_directory":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 19},
            database_is_empty=False,
        )
    if revision == "0018_inventory_stock_roles":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 18},
            database_is_empty=False,
        )
    if revision == "0017_inventory_intelligence":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 17},
            database_is_empty=False,
        )
    if revision == "0016_inventory_acquisition":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 16},
            database_is_empty=False,
        )
    if revision == "0015_purchases_fifo":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 15},
            database_is_empty=False,
        )
    if revision == "0014_structured_inventory_feeding":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 14},
            database_is_empty=False,
        )
    if revision == "0013_password_recovery":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 13},
            database_is_empty=False,
        )
    if revision == "0012_account_reminder_inventory":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 12},
            database_is_empty=False,
        )
    if revision == "0011_product_experience":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 11},
            database_is_empty=False,
        )
    if revision == "0010_multispecies_foundation":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 10},
            database_is_empty=False,
        )
    if revision == "0009_operational_workflows":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 9},
            database_is_empty=False,
        )
    if revision == "0008_local_backups":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 8},
            database_is_empty=False,
        )
    if revision == "0007_profile_photos":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 7},
            database_is_empty=False,
        )
    if revision == "0006_enclosures":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 6},
            database_is_empty=False,
        )
    if revision == "0005_animal_profiles":
        return evaluate_compatibility(
            {"manifest_version": 1, "relational_schema_version": 5},
            database_is_empty=False,
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


def inspect_runtime_compatibility(engine: Engine | Connection) -> CompatibilityReport:
    try:
        with engine.connect() if isinstance(engine, Engine) else nullcontext(engine) as connection:
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


def inspect_event_contracts(engine: Engine | Connection) -> CompatibilityReport:
    """Reject normal startup when any persisted event contract is unknown."""
    contract = "unavailable contract identity"
    try:
        with engine.connect() if isinstance(engine, Engine) else nullcontext(engine) as connection:
            contracts = connection.exec_driver_sql(
                "SELECT DISTINCT event_type, schema_version FROM domain_events "
            ).all()
        for event_type, schema_version in contracts:
            valid_type = isinstance(event_type, str) and bool(
                re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,127}", event_type)
            )
            valid_version = type(schema_version) is int and 0 < schema_version <= 2**63 - 1
            contract = (
                f"{event_type if valid_type else '<invalid event type>'} "
                f"v{schema_version if valid_version else '<invalid version>'}"
            )
            if not valid_type or not valid_version:
                raise ValueError("Malformed event contract identity.")
            production_event_registry.payload_type(event_type, schema_version)
    except UnknownEventContractError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "event_contract_unknown",
            "Stored event history requires a compatible application release.",
            f"Unsupported event contract {contract}; "
            "use a compatible release or verified recovery.",
        )
    except SQLAlchemyError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "event_contract_storage_error",
            "Stored event history could not be inspected safely.",
            "Event-contract inspection encountered a storage error; "
            "check storage availability and schema using the verified recovery procedure.",
        )
    except (TypeError, ValueError):
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "event_contract_invalid",
            "Stored event history could not be inspected safely.",
            f"Invalid event contract {contract}; inspect storage using verified recovery.",
        )
    return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")


inspect_household_event_contracts = inspect_event_contracts


def inspect_required_profile_identities(engine: Engine | Connection) -> CompatibilityReport:
    """Inspect every identity-bearing event, including corrected and voided history."""
    contract = "unknown"
    identity = "malformed identity"
    try:
        with engine.connect() if isinstance(engine, Engine) else nullcontext(engine) as connection:
            # Only trusted registry entries determine which contracts require identities.
            for event_type, version in production_event_registry.required_identity_contracts:
                rows = connection.exec_driver_sql(
                    "SELECT payload_json FROM domain_events "
                    "WHERE event_type=? AND schema_version=?",
                    (event_type, version),
                )
                registration = production_event_registry.registration(event_type, version)
                extractor = registration.required_identity_extractor
                assert extractor is not None
                for row in rows:
                    contract = f"{event_type} v{version}"
                    identity = "malformed identity"
                    payload = json.loads(row[0])
                    if not isinstance(payload, dict):
                        raise ValueError("Event payload must be an object.")
                    group = payload.get("animal_type", payload.get("group"))
                    profile_version = payload.get("capability_profile_version")
                    if event_type == "animal.registered" and version == 1:
                        identity = "snake.v1"
                    elif isinstance(group, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", group):
                        identity = (
                            f"{group}.v{profile_version}"
                            if type(profile_version) is int and 0 < profile_version <= 2**63 - 1
                            else f"workflow:{group}"
                        )
                    extractor(payload)
    except SQLAlchemyError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "embedded_identity_storage_error",
            "Stored history could not be inspected safely.",
            "Required-identity inspection encountered a storage error; "
            "check storage availability and schema using the verified recovery procedure.",
        )
    except (TypeError, ValueError, LookupError) as error:
        unsupported = isinstance(error, LookupError) or isinstance(
            error.__cause__, UnknownCapabilityProfileError
        )
        failure = "unsupported identity" if unsupported else "invalid event payload or identity"
        return CompatibilityReport(
            CompatibilityMode.RECOVERY_REQUIRED,
            "embedded_identity_incompatible" if unsupported else "embedded_identity_invalid",
            "Stored history requires compatible profile support or operator recovery.",
            f"Inspect {contract} ({identity}): {failure}; "
            "use a compatible release or verified recovery procedure.",
        )
    return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")


def inspect_projection_compatibility(
    engine: Engine | Connection, registry: ProjectionRegistry = production_projection_registry
) -> CompatibilityReport:
    """Reject startup when stored projection code is newer or unknown."""
    try:
        with engine.connect() if isinstance(engine, Engine) else nullcontext(engine) as connection:
            definitions = connection.exec_driver_sql(
                "SELECT projection_name,projection_schema_version,handler_version "
                "FROM projection_definitions"
            ).all()
        for name, schema_version, handler_version in definitions:
            try:
                registered = registry.definition(str(name))
            except KeyError:
                return _report(
                    CompatibilityMode.RECOVERY_REQUIRED,
                    "projection_definition_unknown",
                    "Stored projections require a compatible application release.",
                )
            if (
                int(schema_version) > registered.schema_version
                or int(handler_version) > registered.handler_version
            ):
                return _report(
                    CompatibilityMode.RECOVERY_REQUIRED,
                    "projection_definition_newer",
                    "Stored projections require a compatible application release.",
                )
    except (SQLAlchemyError, TypeError, ValueError):
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "projection_definition_inspection_failed",
            "Stored projections could not be inspected safely.",
        )
    return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")


def inspect_local_taxonomy(connection: Connection) -> CompatibilityReport:
    """Fail closed before mutable startup if X2 selection or references are inconsistent."""
    try:
        tables = set(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).scalars()
        )
        required = {
            "taxonomy_selection",
            "taxonomy_generations",
            "taxonomy_changes",
            "taxonomy_overlay",
            "taxonomy_facts",
            "taxonomy_search",
            "taxonomy_search_keys",
            "taxonomy_publications",
            "taxonomy_generation_publications",
            "taxonomy_conflicts",
        }
        if not required <= tables:
            raise ValueError("Missing X2 reference structures.")
        connection.exec_driver_sql("SELECT taxon_id,search_rowid FROM taxonomy_search_keys LIMIT 1")
        connection.exec_driver_sql(
            "SELECT taxon_id,source_effective_at,payload FROM taxonomy_publications LIMIT 1"
        )
        connection.exec_driver_sql(
            "SELECT generation_id FROM taxonomy_generation_publications LIMIT 1"
        )
        connection.exec_driver_sql("SELECT search_rowid FROM taxonomy_facts LIMIT 1")
        rows = connection.exec_driver_sql(
            "SELECT s.generation_id,s.reconciled_revision,g.state,p.generation_id "
            "FROM taxonomy_selection s LEFT JOIN taxonomy_generations g "
            "ON s.generation_id=g.generation_id LEFT JOIN taxonomy_generation_publications p "
            "ON p.generation_id=s.generation_id WHERE s.singleton=1"
        ).all()
        if len(rows) != 1 or (
            rows[0][0] is not None and (rows[0][2] != "ready" or rows[0][3] is None)
        ):
            raise ValueError("Invalid active reference generation.")
        revision = connection.exec_driver_sql(
            "SELECT coalesce(max(revision),0) FROM taxonomy_changes"
        ).scalar_one()
        if not 0 <= rows[0][1] <= revision:
            raise ValueError("Invalid reference reconciliation watermark.")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise ValueError("Unresolved durable references.")
        return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")
    except (SQLAlchemyError, TypeError, ValueError):
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "taxonomy_reference_incompatible",
            "Local taxonomy requires compatible storage or operator recovery.",
        )


def inspect_startup_compatibility(
    engine: Engine,
    registry: ProjectionRegistry = production_projection_registry,
    *,
    reference_inspections: tuple[Callable[[Connection], CompatibilityReport], ...] = (),
) -> CompatibilityReport:
    """Inspect a single snapshot before mutable initialization or ordinary work."""
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            supported_profile_release_manifest(projections=registry)
            for inspect in (
                inspect_database_compatibility,
                inspect_runtime_compatibility,
                inspect_event_contracts,
                inspect_required_profile_identities,
                lambda connection: inspect_projection_compatibility(connection, registry),
                *reference_inspections,
                inspect_local_taxonomy,
            ):
                result = inspect(connection)
                if not result.normal_readiness:
                    return result
            return _report(CompatibilityMode.NORMAL, "compatible", "The application is ready.")
    except SQLAlchemyError:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_storage_error",
            "Stored data could not be inspected safely.",
            "Compatibility inspection encountered a storage error; "
            "check storage availability using the verified recovery procedure.",
        )
    except Exception:
        return _report(
            CompatibilityMode.RECOVERY_REQUIRED,
            "compatibility_inspection_failed",
            "Stored data could not be inspected safely.",
            "Compatibility inspection incomplete; check trusted release metadata and "
            "required inspection support before retrying startup.",
        )
