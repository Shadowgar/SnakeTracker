from __future__ import annotations

import pytest

from snaketracker.bootstrap.compatibility import (
    CompatibilityMode,
    evaluate_compatibility,
)


@pytest.mark.parametrize(
    ("metadata", "database_is_empty", "expected_mode"),
    [
        (
            {"manifest_version": 1, "relational_schema_version": 1},
            False,
            CompatibilityMode.NORMAL,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 0},
            False,
            CompatibilityMode.MIGRATION_REQUIRED,
        ),
        (None, True, CompatibilityMode.BOOTSTRAP_ALLOWED),
        (None, False, CompatibilityMode.RECOVERY_REQUIRED),
        (
            {"manifest_version": 2, "relational_schema_version": 1},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 2},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": -1},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        ({"manifest_version": "invalid"}, False, CompatibilityMode.RECOVERY_REQUIRED),
    ],
)
def test_compatibility_modes_are_conservative(
    metadata: dict[str, object] | None,
    database_is_empty: bool,
    expected_mode: CompatibilityMode,
) -> None:
    report = evaluate_compatibility(metadata, database_is_empty=database_is_empty)

    assert report.mode is expected_mode
    assert report.normal_readiness is (expected_mode is CompatibilityMode.NORMAL)


def test_newer_schema_reason_is_safe_and_stable() -> None:
    report = evaluate_compatibility(
        {"manifest_version": 1, "relational_schema_version": 99},
        database_is_empty=False,
    )

    assert report.reason_code == "relational_schema_too_new"
    assert report.public_detail == "Stored data requires a newer compatible application."
    assert "99" not in report.public_detail
