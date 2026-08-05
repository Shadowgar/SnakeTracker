"""Application-owned database health interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DatabaseHealthPort(Protocol):
    def ping(self) -> bool: ...

    def quick_check(self) -> str: ...
