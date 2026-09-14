"""Universal biological directory and keeper-confirmed Animal links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.application.animals import AnimalCurrentProjection
from snaketracker.domains.animals.contracts import AnimalTaxonLinkedV1
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)

SUPPORTED_GROUPS = frozenset({"snake", "lizard", "spider", "scorpion", "plant"})
ANIMAL_GROUPS = SUPPORTED_GROUPS - {"plant"}


class DirectoryValidationError(ValueError):
    """Directory input or a keeper-confirmed link is invalid."""


class ProviderUnavailableError(RuntimeError):
    """The optional provider cannot complete a bounded lookup."""


@dataclass(frozen=True, slots=True)
class ProviderTaxon:
    provider: str
    provider_id: str
    source_url: str
    supported_group: str
    accepted_scientific_name: str
    preferred_common_name: str | None = None
    authorship: str | None = None
    alternative_common_names: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    taxonomic_status: str = "accepted"
    rank: str | None = None
    kingdom: str | None = None
    phylum_division: str | None = None
    class_name: str | None = None
    order_name: str | None = None
    family: str | None = None
    genus: str | None = None
    species: str | None = None
    infra_rank: str | None = None
    image_source_url: str | None = None
    image_creator: str | None = None
    image_attribution: str | None = None
    image_license_code: str | None = None
    image_license_url: str | None = None


@dataclass(frozen=True, slots=True)
class TaxonRecord:
    taxon_id: UUID
    supported_group: str
    accepted_scientific_name: str
    preferred_common_name: str | None
    authorship: str | None
    alternative_common_names: tuple[str, ...]
    synonyms: tuple[str, ...]
    taxonomic_status: str
    rank: str | None
    kingdom: str | None
    phylum_division: str | None
    class_name: str | None
    order_name: str | None
    family: str | None
    genus: str | None
    species: str | None
    infra_rank: str | None
    provider: str
    provider_id: str
    source_url: str
    retrieved_at: datetime
    refreshed_at: datetime
    stale: bool
    image_source_url: str | None = None
    image_creator: str | None = None
    image_attribution: str | None = None
    image_license_code: str | None = None
    image_license_url: str | None = None

    @property
    def display_name(self) -> str:
        return self.preferred_common_name or self.accepted_scientific_name


@dataclass(frozen=True, slots=True)
class LinkedTaxon:
    animal_id: UUID
    taxon: TaxonRecord
    confirmed_scientific_name: str
    confirmed_common_name: str | None
    link_event_id: UUID
    stream_version: int


@dataclass(frozen=True, slots=True)
class DirectorySearchResult:
    records: tuple[TaxonRecord, ...]
    state: str
    message: str | None = None


class TaxonomyProvider(Protocol):
    provider_name: str

    def search(self, query: str, group: str, *, limit: int) -> tuple[ProviderTaxon, ...]: ...

    def detail(self, provider_id: str, group: str) -> ProviderTaxon: ...


class TaxonRepository(SynchronousProjection, Protocol):
    def search(
        self, query: str, group: str, *, limit: int, stale_after: datetime
    ) -> tuple[TaxonRecord, ...]: ...

    def upsert(self, candidate: ProviderTaxon, *, observed_at: datetime) -> TaxonRecord: ...

    def get(self, taxon_id: UUID, *, stale_after: datetime) -> TaxonRecord | None: ...

    def linked_for(
        self, household_id: UUID, animal_id: UUID, *, stale_after: datetime
    ) -> LinkedTaxon | None: ...


@dataclass(frozen=True, slots=True)
class LinkAnimalTaxonCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    taxon_id: UUID
    correlation_id: UUID
    idempotency_key: str


class SpeciesDirectoryService:
    """Own local-first search, optional provider discovery, and Animal link facts."""

    def __init__(
        self,
        repository: TaxonRepository,
        provider: TaxonomyProvider,
        *,
        event_store: EventStore,
        animal_projection: AnimalCurrentProjection,
        cache_ttl: timedelta = timedelta(days=30),
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._event_store = event_store
        self._animal_projection = animal_projection
        self._cache_ttl = cache_ttl

    def search(
        self, query_value: str, group_value: str, *, limit: int = 10
    ) -> DirectorySearchResult:
        query, group = _validated_search(query_value, group_value, limit)
        now = datetime.now(UTC)
        stale_after = now - self._cache_ttl
        cached = self._repository.search(query, group, limit=limit, stale_after=stale_after)
        if cached and not any(record.stale for record in cached):
            return DirectorySearchResult(cached, "cached")
        try:
            candidates = self._provider.search(query, group, limit=limit)
        except ProviderUnavailableError:
            if cached:
                return DirectorySearchResult(
                    cached,
                    "cached_stale",
                    "Live species search is unavailable. Showing saved results.",
                )
            return DirectorySearchResult(
                (),
                "unavailable",
                "Species search is temporarily unavailable. You can enter the species manually.",
            )
        records = tuple(self._repository.upsert(item, observed_at=now) for item in candidates)
        return DirectorySearchResult(records, "live" if records else "empty")

    def get(self, taxon_id: UUID) -> TaxonRecord | None:
        return self._repository.get(taxon_id, stale_after=datetime.now(UTC) - self._cache_ttl)

    def refresh_detail(self, taxon_id: UUID) -> TaxonRecord | None:
        record = self.get(taxon_id)
        if record is None or record.provider != self._provider.provider_name:
            return record
        try:
            candidate = self._provider.detail(record.provider_id, record.supported_group)
        except ProviderUnavailableError:
            return record
        return self._repository.upsert(candidate, observed_at=datetime.now(UTC))

    def linked_for(self, household_id: UUID, animal_id: UUID) -> LinkedTaxon | None:
        return self._repository.linked_for(
            household_id, animal_id, stale_after=datetime.now(UTC) - self._cache_ttl
        )

    def link_animal(self, command: LinkAnimalTaxonCommand) -> LinkedTaxon:
        animal = self._animal_projection.profile_for(command.household_id, command.animal_id)
        if animal is None:
            raise DirectoryValidationError("Animal not found.")
        taxon = self.refresh_detail(command.taxon_id)
        if taxon is None or taxon.supported_group == "plant":
            raise DirectoryValidationError("Select a valid Animal species result.")
        if taxon.supported_group != animal.animal_type:
            raise DirectoryValidationError("The selected species does not match this Animal type.")
        existing = self.linked_for(command.household_id, command.animal_id)
        if existing is not None and existing.taxon.taxon_id == taxon.taxon_id:
            return existing
        now = datetime.now(UTC)
        payload = AnimalTaxonLinkedV1(
            taxon_id=taxon.taxon_id,
            group=taxon.supported_group,
            accepted_scientific_name=taxon.accepted_scientific_name,
            preferred_common_name=taxon.preferred_common_name,
            provider=taxon.provider,
            provider_id=taxon.provider_id,
        )
        candidate = DomainEvent(
            event_id=uuid4(),
            household_id=command.household_id,
            stream_type="animal",
            stream_id=command.animal_id,
            stream_version=animal.stream_version + 1,
            event_type="animal.taxon_linked",
            schema_version=1,
            occurred_at=now,
            recorded_at=now,
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=None,
            idempotency_key=command.idempotency_key,
            subjects=(EventSubject("animal", command.animal_id, "primary", 0),),
            title="Animal species linked",
            description=None,
            payload=payload,
            metadata={},
            notes=None,
            checksum="",
        )
        event = candidate.with_checksum(event_checksum(candidate))
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(
                    StreamAppend(
                        StreamKey(command.household_id, "animal", command.animal_id),
                        expected_version=animal.stream_version,
                        events=(event,),
                    ),
                ),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="animals.link_taxon",
                    idempotency_key=command.idempotency_key,
                    command_hash=canonical_command_hash(
                        {"animal_id": str(command.animal_id), "taxon_id": str(command.taxon_id)}
                    ),
                    correlation_id=command.correlation_id,
                    stored_response={"animal_id": str(command.animal_id)},
                    stored_response_schema_version=1,
                    created_at=now,
                    expires_at=now + timedelta(days=90),
                ),
                synchronous_projections=(self._animal_projection, self._repository),
            )
        )
        stored_animal_id = result.stored_response.get("animal_id")
        if stored_animal_id != str(command.animal_id):
            raise RuntimeError("Animal taxon linking did not retain its stored response.")
        linked = self.linked_for(command.household_id, command.animal_id)
        if linked is None:
            raise RuntimeError("Animal taxon linking did not project current state.")
        return linked


def _validated_search(query_value: str, group_value: str, limit: int) -> tuple[str, str]:
    query = " ".join(query_value.strip().split())
    group = group_value.strip().lower()
    if group not in SUPPORTED_GROUPS:
        raise DirectoryValidationError("Choose a supported directory group.")
    if len(query) < 2:
        raise DirectoryValidationError("Enter at least 2 characters.")
    if len(query) > 100 or limit < 1 or limit > 20:
        raise DirectoryValidationError("Species search is too large.")
    return query, group
