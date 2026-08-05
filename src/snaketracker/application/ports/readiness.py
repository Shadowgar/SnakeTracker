"""Application-owned readiness contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    is_ready: bool
    reason_code: str | None

    @classmethod
    def ready(cls) -> ReadinessResult:
        return cls(is_ready=True, reason_code=None)

    @classmethod
    def unavailable(cls, reason_code: str) -> ReadinessResult:
        return cls(is_ready=False, reason_code=reason_code)


class ReadinessPort(Protocol):
    def check(self) -> ReadinessResult: ...


class HealthMetricsPort(Protocol):
    def set_readiness(self, *, ready: bool) -> None: ...

    def render(self) -> bytes: ...
