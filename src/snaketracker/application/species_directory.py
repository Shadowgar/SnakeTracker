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
REFERENCE_IMAGE_LICENSES = frozenset({"cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"})


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
    image_provider_record_id: str | None = None
    image_source_page_url: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceImageCandidate:
    """A policy-eligible licensed image proposed by a bounded external provider."""

    provider: str
    provider_record_id: str
    download_url: str
    source_page_url: str
    creator: str
    attribution: str
    license_code: str
    license_url: str
    retrieved_at: datetime
    kind: str = "photograph"


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
    image_local_filename: str | None = None
    image_local_media_type: str | None = None
    image_local_byte_size: int | None = None
    image_local_sha256: str | None = None
    image_cached_at: datetime | None = None
    image_provider: str | None = None
    image_provider_record_id: str | None = None
    image_source_page_url: str | None = None
    image_retrieved_at: datetime | None = None
    image_kind: str = "photograph"
    image_resolution_state: str | None = None
    image_checked_at: datetime | None = None

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


@dataclass(frozen=True, slots=True)
class CachedReferenceImage:
    filename: str
    media_type: str
    byte_size: int
    sha256: str
    cached_at: datetime
    content: bytes


@dataclass(frozen=True, slots=True)
class ReferenceImage:
    taxon_id: UUID
    content: bytes
    media_type: str
    creator: str
    attribution: str
    license_code: str
    license_url: str
    source_url: str
    provider: str
    provider_id: str
    cached_at: datetime
    source_page_url: str
    retrieved_at: datetime
    kind: str


@dataclass(frozen=True, slots=True)
class IdentitySuggestions:
    morphs: tuple[str, ...]
    genetics: tuple[str, ...]


class TaxonomyProvider(Protocol):
    provider_name: str

    def search(self, query: str, group: str, *, limit: int) -> tuple[ProviderTaxon, ...]: ...

    def detail(self, provider_id: str, group: str) -> ProviderTaxon: ...


class ReferenceImageProvider(Protocol):
    provider_name: str

    def find(self, taxon: TaxonRecord) -> ReferenceImageCandidate | None: ...


class ReferenceImageCache(Protocol):
    def cache(self, taxon_id: UUID, source_url: str) -> CachedReferenceImage: ...

    def load(self, filename: str, expected_sha256: str) -> bytes: ...


class TaxonRepository(SynchronousProjection, Protocol):
    def search(
        self, query: str, group: str, *, limit: int, stale_after: datetime
    ) -> tuple[TaxonRecord, ...]: ...

    def upsert(self, candidate: ProviderTaxon, *, observed_at: datetime) -> TaxonRecord: ...

    def get(self, taxon_id: UUID, *, stale_after: datetime) -> TaxonRecord | None: ...

    def linked_for(
        self, household_id: UUID, animal_id: UUID, *, stale_after: datetime
    ) -> LinkedTaxon | None: ...

    def mark_image_cached(self, taxon_id: UUID, image: CachedReferenceImage) -> None: ...

    def store_image_candidate(
        self, taxon_id: UUID, candidate: ReferenceImageCandidate
    ) -> TaxonRecord: ...

    def mark_image_resolution(self, taxon_id: UUID, state: str, checked_at: datetime) -> None: ...

    def discard_image_candidate(self, taxon_id: UUID, source_url: str) -> None: ...

    def identity_suggestions(self, household_id: UUID, taxon_id: UUID) -> IdentitySuggestions: ...


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
        reference_image_cache: ReferenceImageCache | None = None,
        reference_image_providers: tuple[ReferenceImageProvider, ...] = (),
        cache_ttl: timedelta = timedelta(days=30),
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._event_store = event_store
        self._animal_projection = animal_projection
        self._cache_ttl = cache_ttl
        self._reference_image_cache = reference_image_cache
        self._reference_image_providers = reference_image_providers

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

    def identity_suggestions(self, household_id: UUID, taxon_id: UUID) -> IdentitySuggestions:
        return self._repository.identity_suggestions(household_id, taxon_id)

    def reference_image(self, taxon_id: UUID) -> ReferenceImage | None:
        taxon = self.get(taxon_id)
        if taxon is None or self._reference_image_cache is None:
            return None
        now = datetime.now(UTC)
        if (
            not _has_approved_image(taxon)
            and _image_lookup_due(taxon, now)
            and taxon.provider == self._provider.provider_name
        ):
            taxon = self.refresh_detail(taxon_id) or taxon
        if _has_approved_image(taxon):
            cached = self._load_or_cache(taxon)
            if cached is not None:
                return _reference_image(taxon, cached)
            assert taxon.image_source_url is not None
            self._repository.discard_image_candidate(taxon_id, taxon.image_source_url)
            taxon = self.get(taxon_id)
            if taxon is None:
                return None
        lookup_due = _image_lookup_due(taxon, now)
        if lookup_due:
            unavailable = False
            for provider in self._reference_image_providers:
                try:
                    candidate = provider.find(taxon)
                except ProviderUnavailableError:
                    unavailable = True
                    continue
                if candidate is None:
                    continue
                try:
                    cached = self._reference_image_cache.cache(taxon_id, candidate.download_url)
                except ProviderUnavailableError:
                    unavailable = True
                    continue
                taxon = self._repository.store_image_candidate(taxon_id, candidate)
                self._repository.mark_image_cached(taxon_id, cached)
                return _reference_image(taxon, cached)
            else:
                self._repository.mark_image_resolution(
                    taxon_id, "unavailable" if unavailable else "no_match", now
                )
        return None

    def _load_or_cache(self, taxon: TaxonRecord) -> CachedReferenceImage | None:
        assert self._reference_image_cache is not None
        assert taxon.image_source_url is not None
        cached_at = taxon.image_cached_at
        content: bytes | None = None
        if taxon.image_local_filename and taxon.image_local_sha256 and cached_at is not None:
            try:
                content = self._reference_image_cache.load(
                    taxon.image_local_filename, taxon.image_local_sha256
                )
            except ProviderUnavailableError:
                content = None
        if content is None:
            try:
                cached = self._reference_image_cache.cache(taxon.taxon_id, taxon.image_source_url)
            except ProviderUnavailableError:
                return None
            self._repository.mark_image_cached(taxon.taxon_id, cached)
            return cached
        assert cached_at is not None
        return CachedReferenceImage(
            filename=taxon.image_local_filename or f"{taxon.taxon_id}.webp",
            media_type=taxon.image_local_media_type or "image/webp",
            byte_size=len(content),
            sha256=taxon.image_local_sha256 or "",
            cached_at=cached_at,
            content=content,
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


def _has_approved_image(taxon: TaxonRecord) -> bool:
    return bool(
        taxon.image_source_url
        and taxon.image_creator
        and taxon.image_attribution
        and taxon.image_license_code in REFERENCE_IMAGE_LICENSES
        and taxon.image_license_url
    )


def _image_lookup_due(taxon: TaxonRecord, now: datetime) -> bool:
    return bool(
        not _has_approved_image(taxon)
        and (
            taxon.image_checked_at is None
            or taxon.image_resolution_state is None
            or (
                taxon.image_resolution_state == "no_match"
                and taxon.image_checked_at < now - timedelta(days=30)
            )
            or (
                taxon.image_resolution_state == "unavailable"
                and taxon.image_checked_at < now - timedelta(hours=1)
            )
        )
    )


def _reference_image(taxon: TaxonRecord, cached: CachedReferenceImage) -> ReferenceImage:
    assert taxon.image_source_url is not None
    assert taxon.image_creator is not None
    assert taxon.image_attribution is not None
    assert taxon.image_license_code in REFERENCE_IMAGE_LICENSES
    assert taxon.image_license_url is not None
    return ReferenceImage(
        taxon_id=taxon.taxon_id,
        content=cached.content,
        media_type=cached.media_type,
        creator=taxon.image_creator,
        attribution=taxon.image_attribution,
        license_code=taxon.image_license_code,
        license_url=taxon.image_license_url,
        source_url=taxon.image_source_url,
        provider=taxon.image_provider or taxon.provider,
        provider_id=taxon.image_provider_record_id or taxon.provider_id,
        cached_at=cached.cached_at,
        source_page_url=taxon.image_source_page_url or taxon.source_url,
        retrieved_at=taxon.image_retrieved_at or taxon.retrieved_at,
        kind=taxon.image_kind,
    )
