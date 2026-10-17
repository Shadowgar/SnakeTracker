"""Local taxonomy contracts; classification never grants Animal capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class TaxonomyConflictError(ValueError):
    """A durable identity or selection decision requires explicit resolution."""


@dataclass(frozen=True, slots=True)
class GenerationSource:
    label: str
    provider: str
    source_url: str
    retrieved_at: datetime
    snapshot_at: datetime | None
    checksum: str
    rights: str


@dataclass(frozen=True, slots=True)
class TaxonAncestor:
    taxon_id: UUID
    scientific_name: str
    rank: str | None


@dataclass(frozen=True, slots=True)
class TaxonomyProviderReference:
    provider: str
    provider_id: str
    source_url: str
    qualification_state: str


@dataclass(frozen=True, slots=True)
class TaxonomySummary:
    taxon_id: UUID
    scientific_name: str
    common_name: str | None
    synonyms: tuple[str, ...]
    common_names: tuple[str, ...]
    workflow_group: str | None
    taxonomic_status: str
    classification: tuple[tuple[str, str], ...]
    ancestry: tuple[TaxonAncestor, ...]
    provider: str
    provider_id: str
    source_url: str
    retrieved_at: datetime
    source_effective_at: datetime | None
    revision: int
    reference_state: str
    selection_state: str
    provider_references: tuple[TaxonomyProviderReference, ...] = ()


@dataclass(frozen=True, slots=True)
class IdentityConflict:
    conflict_id: int
    taxon_id: UUID
    kind: str
    details: str
    generation_id: UUID | None


class LocalTaxonomy(Protocol):
    """X3 consumes selected local taxonomy and provenance through this port."""

    def resolve(self, taxon_id: UUID) -> TaxonomySummary | None: ...

    def search(
        self, query: str, *, group: str | None = None, limit: int = 10
    ) -> tuple[TaxonomySummary, ...]: ...
