"""Application readiness policy."""

from __future__ import annotations

from typing import Protocol

from snaketracker.application.ports.database import DatabaseHealthPort
from snaketracker.application.ports.readiness import ReadinessResult


class CompatibilityStatus(Protocol):
    @property
    def normal_readiness(self) -> bool: ...

    reason_code: str


class PlatformReadiness:
    """Combine compatibility and bounded database reachability checks."""

    def __init__(self, *, database: DatabaseHealthPort, compatibility: CompatibilityStatus) -> None:
        self._database = database
        self._compatibility = compatibility

    def check(self) -> ReadinessResult:
        if not self._compatibility.normal_readiness:
            return ReadinessResult.unavailable(self._compatibility.reason_code)
        try:
            database_ready = self._database.ping()
        except Exception:
            return ReadinessResult.unavailable("database_unavailable")
        if not database_ready:
            return ReadinessResult.unavailable("database_unavailable")
        return ReadinessResult.ready()
