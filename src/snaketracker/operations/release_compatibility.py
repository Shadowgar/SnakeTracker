"""Export release declarations without opening a database or claiming qualification."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import sys
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, metadata

from snaketracker.bootstrap.compatibility import (
    CURRENT_MANIFEST_VERSION,
    CURRENT_RELATIONAL_SCHEMA_VERSION,
    MINIMUM_RELATIONAL_SCHEMA_VERSION,
    MINIMUM_SQLITE_VERSION,
    CompatibilityMode,
    evaluate_compatibility,
    supported_profile_release_manifest,
)
from snaketracker.infrastructure.product_experience.projections import product_projection_registry
from snaketracker.platform.events.registry import production_event_registry


def _json_default(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError("Unsupported release metadata value.")


def export_release_compatibility(*, require_build_identity: bool = False) -> str:
    """Return stable JSON for this package/runtime without database or network I/O.

    The configured build identity is a declaration. The release pipeline separately
    verifies it against installed files and the immutable image. No current database,
    migration, rollback, plugin, hardware or owner acceptance is inferred here.
    """
    build_sha = os.environ.get("SNAKETRACKER_BUILD_GIT_SHA") or None
    if build_sha is not None and re.fullmatch(r"[0-9a-f]{40}", build_sha) is None:
        raise ValueError("Build identity must be a full lowercase Git commit hash.")
    if require_build_identity and build_sha is None:
        raise ValueError("A configured build identity is required for release evidence.")
    package = metadata("snaketracker")
    schema_modes = {
        version: evaluate_compatibility(
            {"manifest_version": CURRENT_MANIFEST_VERSION, "relational_schema_version": version},
            database_is_empty=False,
        ).mode
        for version in range(
            MINIMUM_RELATIONAL_SCHEMA_VERSION, CURRENT_RELATIONAL_SCHEMA_VERSION + 1
        )
    }
    upcasters = [
        {"event_type": event_type, "from_version": source, "to_version": source + 1}
        for event_type, version in sorted(production_event_registry.identities)
        for source in sorted(
            production_event_registry.registration(event_type, version).upcasters or {}
        )
    ]
    manifest = {
        "format_version": 1,
        "application": {
            "name": "snaketracker",
            "version": package["Version"],
            "build_git_sha": build_sha,
            "build_identity_status": "declared" if build_sha else "unrecorded",
        },
        "supported_contracts": supported_profile_release_manifest(
            projections=product_projection_registry
        ),
        "relational_schema": {
            "compatibility_manifest_version": CURRENT_MANIFEST_VERSION,
            "current_version": CURRENT_RELATIONAL_SCHEMA_VERSION,
            "minimum_recognized_version": MINIMUM_RELATIONAL_SCHEMA_VERSION,
            "mutable_versions": [
                v for v, mode in schema_modes.items() if mode == CompatibilityMode.NORMAL
            ],
            "migration_required_versions": [
                v
                for v, mode in schema_modes.items()
                if mode == CompatibilityMode.MIGRATION_REQUIRED
            ],
            "scope": "Compatibility metadata versions; migration-path qualification is separate.",
        },
        "event_upcasters": upcasters,
        "event_writes": {
            "status": "partially_declared",
            "scope": "Profile registration writes only; readable contracts do not declare writers.",
        },
        "runtime_requirements": {
            "python": package["Requires-Python"],
            "minimum_sqlite": ".".join(str(part) for part in MINIMUM_SQLITE_VERSION),
        },
        "runtime_observation": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": sys.platform,
            "machine": platform.machine(),
        },
        "plugin_compatibility": {
            "status": "unrecorded",
            "scope": "No enabled-plugin package/API compatibility declaration is supplied.",
        },
        "downgrade_compatibility": {
            "status": "unrecorded",
            "scope": "Requires target-binary and retained schema/event/profile/reference evidence.",
        },
        "qualification": {
            "status": "not_asserted",
            "scope": "This export is metadata, not migration, recovery, security or Pi acceptance.",
        },
    }
    return json.dumps(manifest, default=_json_default, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-build-identity",
        action="store_true",
        help="Fail when SNAKETRACKER_BUILD_GIT_SHA is absent; required for release evidence.",
    )
    arguments = parser.parse_args()
    try:
        document = export_release_compatibility(
            require_build_identity=arguments.require_build_identity
        )
    except PackageNotFoundError:
        parser.error("Application package metadata is unavailable; install the locked application.")
    except ValueError as error:
        parser.error(str(error))
    print(document, end="")


if __name__ == "__main__":
    main()
