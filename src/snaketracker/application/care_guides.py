"""Validated, sourced reference knowledge; never a household care command."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GuideGroup(StrEnum):
    SNAKE = "snake"
    LIZARD = "lizard"
    SPIDER = "spider"
    SCORPION = "scorpion"
    PLANT = "plant"


class GuideSection(StrEnum):
    AT_A_GLANCE = "at_a_glance"
    TEMPERATURE_HUMIDITY = "temperature_humidity"
    FEEDING = "feeding"
    HABITAT_ENCLOSURE = "habitat_enclosure"
    LIGHTING = "lighting"
    WATER_SUBSTRATE = "water_substrate"
    LIFE_STAGE = "life_stage"
    CAUTIONS = "cautions"


SECTION_LABELS = {
    GuideSection.AT_A_GLANCE: "At a glance",
    GuideSection.TEMPERATURE_HUMIDITY: "Temperature & humidity",
    GuideSection.FEEDING: "Feeding",
    GuideSection.HABITAT_ENCLOSURE: "Habitat & enclosure",
    GuideSection.LIGHTING: "Lighting",
    GuideSection.WATER_SUBSTRATE: "Water & substrate",
    GuideSection.LIFE_STAGE: "Life stage",
    GuideSection.CAUTIONS: "Cautions",
}


UNIT_BOUNDS = {
    "c": (-30.0, 80.0),
    "percent": (0.0, 100.0),
    "cm": (0.0, 10000.0),
    "days": (0.0, 3650.0),
    "years": (0.0, 200.0),
    "hours": (0.0, 24.0),
}


class GuideSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    publisher: str = Field(min_length=2, max_length=256)
    title: str = Field(min_length=2, max_length=256)
    url: str = Field(min_length=12, max_length=1024)
    provider_id: str | None = Field(default=None, max_length=128)
    source_type: str = Field(
        pattern=r"^(veterinary|animal_welfare|zoo|botanical|university|government|scientific|specialist)$"
    )
    retrieved_at: datetime
    reviewed_at: datetime
    published_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def safe_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(character.isspace() for character in value)
        ):
            raise ValueError(
                "source URL must be a plain HTTPS page without credentials or fragment"
            )
        return value

    @field_validator("retrieved_at", "reviewed_at", "published_at")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("source timestamps must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.reviewed_at < self.retrieved_at:
            raise ValueError("source review must be after retrieval")
        return self


class GuideClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    section: GuideSection
    fact_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=2, max_length=128)
    value_text: str | None = Field(default=None, min_length=2, max_length=512)
    value_number: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    qualifier: str | None = Field(default=None, max_length=256)
    life_stage: str | None = Field(default=None, max_length=64)
    context: str | None = Field(default=None, max_length=128)
    caution: str | None = Field(default=None, max_length=512)
    scope: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def valid_value(self) -> Self:
        numeric = self.value_number is not None
        ranged = self.minimum is not None or self.maximum is not None
        textual = self.value_text is not None
        if sum((numeric, ranged, textual)) != 1:
            raise ValueError("claim must have exactly one text, number, or range value")
        if ranged and (self.minimum is None or self.maximum is None):
            raise ValueError("range requires both bounds")
        if textual and self.unit is not None:
            raise ValueError("text claim cannot have a numeric unit")
        if (numeric or ranged) and self.unit not in UNIT_BOUNDS:
            raise ValueError("numeric claim requires a supported canonical unit")
        if self.unit is not None:
            lower, upper = UNIT_BOUNDS[self.unit]
            for value in (self.value_number, self.minimum, self.maximum):
                if value is not None and (
                    not math.isfinite(value) or value < lower or value > upper
                ):
                    raise ValueError("claim value is outside its unit bounds")
        if (
            ranged
            and self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("range minimum exceeds maximum")
        if self.fact_key.startswith("toxicity_") and not self.scope:
            raise ValueError("toxicity claims require an explicit affected-species scope")
        return self


class ReviewedGuide(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    biological_group: GuideGroup
    scientific_name: str = Field(min_length=3, max_length=256)
    version: int = Field(ge=1)
    created_at: datetime
    reviewed_at: datetime
    sources: tuple[GuideSource, ...] = Field(min_length=1, max_length=30)
    claims: tuple[GuideClaim, ...] = Field(min_length=1, max_length=150)

    @field_validator("created_at", "reviewed_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("guide timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_guide(self) -> Self:
        if self.created_at > self.reviewed_at:
            raise ValueError("guide review precedes creation")
        source_ids = {source.source_id for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("duplicate source ID")
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate claim ID")
        if any(source.reviewed_at > self.reviewed_at for source in self.sources):
            raise ValueError("source review follows guide review")
        if any(claim.source_id not in source_ids for claim in self.claims):
            raise ValueError("claim links to an unknown source")
        positions: set[tuple[str, str, str, str, str]] = set()
        for claim in self.claims:
            position = (
                claim.source_id,
                claim.fact_key,
                claim.life_stage or "",
                claim.context or "",
                claim.scope or "",
            )
            if position in positions:
                raise ValueError("a source has duplicate positions for one contextual fact")
            positions.add(position)
        if self.biological_group != GuideGroup.PLANT and any(
            claim.fact_key.startswith("plant_") for claim in self.claims
        ):
            raise ValueError("plant claims cannot be attached to an animal guide")
        return self


class GuideBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: int = Field(ge=1, le=1)
    guides: tuple[ReviewedGuide, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_versions(self) -> Self:
        keys = {
            (guide.biological_group, guide.scientific_name, guide.version) for guide in self.guides
        }
        if len(keys) != len(self.guides):
            raise ValueError("duplicate guide version")
        return self


class CareGuideReader(Protocol):
    """Local reviewed-reference reads available to the browser."""

    def current(self, taxon_id: UUID) -> ReviewedGuide | None: ...

    def version(self, taxon_id: UUID, version: int) -> ReviewedGuide | None: ...

    def versions(self, taxon_id: UUID) -> tuple[int, ...]: ...

    def available(self, taxon_id: UUID) -> bool: ...


def format_claim_value(claim: GuideClaim) -> str:
    """Render reviewed canonical values without implying extra precision."""
    if claim.value_text is not None:
        return claim.value_text
    values = (claim.minimum, claim.maximum) if claim.minimum is not None else (claim.value_number,)
    numbers = tuple(_number(value) for value in values if value is not None)
    rendered = "\u2013".join(numbers)
    if claim.unit == "c":
        fahrenheit = "\u2013".join(
            _number(round(value * 9 / 5 + 32, 1)) for value in values if value is not None
        )
        return f"{rendered}°C ({fahrenheit}°F)"
    suffix = {"percent": "%", "cm": " cm", "days": " days", "years": " years", "hours": " hours"}
    return rendered + suffix[claim.unit or ""]


def _number(value: float) -> str:
    return f"{value:g}"


def claim_signature(claim: GuideClaim) -> tuple[object, ...]:
    return (
        claim.value_text,
        claim.value_number,
        claim.minimum,
        claim.maximum,
        claim.unit,
        claim.qualifier,
        claim.caution,
    )


def support_state(claims: tuple[GuideClaim, ...], sources: dict[str, GuideSource]) -> str:
    if len({claim_signature(claim) for claim in claims}) > 1:
        return "Sources differ"
    publishers = {sources[claim.source_id].publisher.casefold() for claim in claims}
    return "Corroborated" if len(publishers) > 1 else "Single source"


def grouped_claims(
    guide: ReviewedGuide,
) -> tuple[tuple[str, tuple[tuple[str, tuple[GuideClaim, ...], str], ...]], ...]:
    """Group same-context source positions while retaining every disagreeing claim."""
    sources = {source.source_id: source for source in guide.sources}
    sections: dict[GuideSection, dict[tuple[str, str, str, str], list[GuideClaim]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for claim in guide.claims:
        sections[claim.section][
            (claim.fact_key, claim.life_stage or "", claim.context or "", claim.scope or "")
        ].append(claim)
    return tuple(
        (
            SECTION_LABELS[section],
            tuple(
                (
                    claims[0].label,
                    tuple(claims),
                    support_state(tuple(claims), sources),
                )
                for _, claims in sorted(sections[section].items())
            ),
        )
        for section in GuideSection
        if sections.get(section)
    )
