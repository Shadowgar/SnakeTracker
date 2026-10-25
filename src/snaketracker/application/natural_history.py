"""Locally retained biological reference; no care recommendations or acquisition."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from snaketracker.application.care_guides import ReviewedGuide


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def plain_text(cls, value: object) -> object:
        if isinstance(value, str) and any(c in value for c in ("<", ">", "\x00")):
            raise ValueError("Reference fields must be plain text.")
        return value


def https(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Source links require plain HTTPS URLs.")
    return value


class DescriptionSection(FrozenModel):
    title: Literal["About this species", "In the wild", "Where it lives", "Identification"]
    text: str = Field(min_length=10, max_length=2400)


class BiologicalContext(FrozenModel):
    kind: Literal[
        "habitat", "distribution", "activity", "diet", "lifespan", "adult_size", "conservation"
    ]
    life_stage: str = Field(min_length=1, max_length=80)
    geography: str = Field(min_length=1, max_length=180)
    sex: str = Field(min_length=1, max_length=80)
    qualifiers: str = Field(default="", max_length=400)
    context: Literal["wild"] = "wild"


class BiologicalFact(BiologicalContext):
    value: str = Field(min_length=1, max_length=500)
    unit: str = Field(default="", max_length=32)
    qualification: str = Field(min_length=10, max_length=1500)


class GuideBiologyBinding(BiologicalContext):
    """Explicit, reviewed semantic classification of an exact immutable guide claim."""

    guide_version: int = Field(gt=0)
    guide_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    claim_id: str = Field(min_length=1, max_length=64)
    origin: str = Field(min_length=12, max_length=1024)
    qualification: str = Field(min_length=10, max_length=1500)

    _origin = field_validator("origin")(https)


class NaturalHistoryVersion(FrozenModel):
    taxon_id: UUID
    origin: str = Field(min_length=12, max_length=1024)
    revision: str = Field(min_length=1, max_length=128)
    revision_url: str = Field(min_length=12, max_length=1024)
    source_title: str = Field(min_length=2, max_length=256)
    attribution: str = Field(min_length=2, max_length=512)
    license: str = Field(min_length=2, max_length=128)
    license_url: str = Field(min_length=12, max_length=1024)
    modifications: str = Field(min_length=2, max_length=1000)
    retrieved_at: datetime
    verified_name: str = Field(min_length=2, max_length=256)
    identity_provider: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    identity_provider_id: str = Field(min_length=1, max_length=128)
    identity_evidence: str = Field(min_length=12, max_length=1024)
    rights_scope: Literal["development", "production"]
    rights_evidence: str = Field(min_length=10, max_length=2400)
    sections: tuple[DescriptionSection, ...] = Field(default=(), max_length=8)
    claims: tuple[BiologicalFact, ...] = Field(default=(), max_length=32)
    guide_bindings: tuple[GuideBiologyBinding, ...] = Field(default=(), max_length=64)

    _urls = field_validator("origin", "revision_url", "license_url", "identity_evidence")(https)

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Retrieval requires an explicit timezone.")
        return value

    @model_validator(mode="after")
    def content_required(self) -> Self:
        if not self.sections and not self.claims and not self.guide_bindings:
            raise ValueError("At least one retained description or qualified claim is required.")
        if len({s.title for s in self.sections}) != len(self.sections):
            raise ValueError("Description sections must be unique.")
        return self

    @property
    def payload(self) -> str:
        return self.model_dump_json()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.payload.encode()).hexdigest()


class NaturalHistoryReader(Protocol):
    def published(
        self, taxon_id: UUID, *, include_development: bool = False
    ) -> tuple[NaturalHistoryVersion, ...]: ...


@dataclass(frozen=True, order=True)
class BiologicalEvidence:
    origin: str
    reference: str
    qualification: str


@dataclass(frozen=True)
class BiologicalPosition:
    fact: BiologicalFact
    origins: tuple[str, ...]
    references: tuple[str, ...]
    guide_claim_ids: tuple[str, ...] = ()
    evidence: tuple[BiologicalEvidence, ...] = ()


@dataclass(frozen=True)
class BiologicalGroup:
    kind: str
    context: BiologicalContext
    positions: tuple[BiologicalPosition, ...]

    @property
    def state(self) -> str:
        if len(self.positions) > 1:
            return "Sources differ"
        return "Multiple sources" if len(self.positions[0].origins) > 1 else "Single source"


def guide_digest(guide: ReviewedGuide) -> str:
    payload = json.dumps(
        guide.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def biological_groups(
    versions: tuple[NaturalHistoryVersion, ...],
    guide: ReviewedGuide | None,
    *,
    retained_guides: tuple[ReviewedGuide, ...] = (),
) -> tuple[BiologicalGroup, ...]:
    """Combine equivalent positions without interpreting unknown or captive legacy claims."""
    guides = {g.version: g for g in retained_guides}
    if guide is not None:
        guides[guide.version] = guide
    rows: list[tuple[BiologicalFact, str, str, str | None]] = []
    for version in versions:
        rows.extend((fact, version.origin, version.revision_url, None) for fact in version.claims)
        for binding in version.guide_bindings:
            bound_guide = guides.get(binding.guide_version)
            if bound_guide is None or binding.guide_sha256 != guide_digest(bound_guide):
                continue
            claim = next((c for c in bound_guide.claims if c.claim_id == binding.claim_id), None)
            # Explicit source-specific classification is required; captive and unknown context
            # always remain in their original guide. No name/keyword inference is permitted.
            if claim is None or claim.context != "wild":
                continue
            source = next(s for s in bound_guide.sources if s.source_id == claim.source_id)
            fact = BiologicalFact(
                **binding.model_dump(include=set(BiologicalContext.model_fields)),
                value=(
                    claim.value_text
                    if claim.value_text is not None
                    else f"{claim.value_number:g}"
                    if claim.value_number is not None
                    else f"{claim.minimum:g}-{claim.maximum:g}"
                ),
                unit=claim.unit or "",
                qualification=binding.qualification,
            )
            rows.append((fact, binding.origin, source.url, claim.claim_id))
    groups: dict[str, dict[tuple[str, str], list[tuple[BiologicalFact, str, str, str | None]]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    contexts: dict[str, BiologicalContext] = {}
    for fact, origin, reference, claim_id in rows:
        context = BiologicalContext(**fact.model_dump(include=set(BiologicalContext.model_fields)))
        key = context.model_dump_json()
        contexts[key] = context
        groups[key][(fact.value, fact.unit)].append((fact, origin, reference, claim_id))
    return tuple(
        BiologicalGroup(
            contexts[key].kind,
            contexts[key],
            tuple(
                BiologicalPosition(
                    items[0][0],
                    tuple(sorted({i[1] for i in items})),
                    tuple(sorted({i[2] for i in items})),
                    tuple(sorted({i[3] for i in items if i[3] is not None})),
                    tuple(
                        sorted({BiologicalEvidence(i[1], i[2], i[0].qualification) for i in items})
                    ),
                )
                for items in positions.values()
            ),
        )
        for key, positions in groups.items()
    )
