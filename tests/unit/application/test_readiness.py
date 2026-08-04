from __future__ import annotations

from dataclasses import dataclass

from snaketracker.application.readiness import PlatformReadiness


@dataclass
class StubCompatibility:
    normal_readiness: bool
    reason_code: str


class StubDatabase:
    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.result

    def quick_check(self) -> str:
        return "ok"


def test_readiness_rejects_incompatible_state_before_database_check() -> None:
    readiness = PlatformReadiness(
        database=StubDatabase(error=AssertionError("must not be called")),
        compatibility=StubCompatibility(False, "relational_schema_too_new"),
    )

    assert readiness.check().reason_code == "relational_schema_too_new"


def test_readiness_reports_database_failure_without_exception_detail() -> None:
    readiness = PlatformReadiness(
        database=StubDatabase(error=RuntimeError("private database detail")),
        compatibility=StubCompatibility(True, "compatible"),
    )

    result = readiness.check()

    assert result.is_ready is False
    assert result.reason_code == "database_unavailable"


def test_readiness_accepts_compatible_responsive_database() -> None:
    readiness = PlatformReadiness(
        database=StubDatabase(), compatibility=StubCompatibility(True, "compatible")
    )

    assert readiness.check().is_ready is True


def test_readiness_rejects_false_database_probe() -> None:
    readiness = PlatformReadiness(
        database=StubDatabase(result=False),
        compatibility=StubCompatibility(True, "compatible"),
    )

    assert readiness.check().reason_code == "database_unavailable"
