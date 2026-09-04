"""Household-scoped keeper search application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class SearchValidationError(ValueError):
    """The submitted search query is not safe or useful."""


class SearchUnavailableError(RuntimeError):
    """The active search generation is absent or rebuilding."""


@dataclass(frozen=True, slots=True)
class SearchResult:
    kind: str
    title: str
    body: str
    route: str
    effective_at: str | None


class SearchRepository(Protocol):
    def search(
        self,
        household_id: UUID,
        capabilities: frozenset[str],
        query: str,
        *,
        limit: int,
    ) -> tuple[SearchResult, ...]: ...


class SearchService:
    def __init__(self, repository: SearchRepository) -> None:
        self._repository = repository

    def search(
        self, household_id: UUID, capabilities: frozenset[str], query: str
    ) -> tuple[SearchResult, ...]:
        normalized = " ".join(query.split())
        if not normalized:
            return ()
        if len(normalized) > 100:
            raise SearchValidationError("Search queries are limited to 100 characters.")
        return self._repository.search(household_id, capabilities, normalized, limit=50)
