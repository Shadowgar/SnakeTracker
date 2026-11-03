"""Read-only, exact-species captive-care choices; no inferred schedule authority."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from snaketracker.application.care_guides import (
    GuideClaim,
    GuideSource,
    ReviewedGuide,
    support_state,
)


@dataclass(frozen=True, slots=True)
class FeedingOption:
    claim: GuideClaim
    source: GuideSource
    interval_days: int | None
    support: str


def feeding_options(
    guide: ReviewedGuide | None, *, animal_group: str, scientific_name: str | None
) -> tuple[FeedingOption, ...]:
    """Only explicit captive feeding positions for the exact linked species qualify.

    Text and ranges remain visible competing positions, never inferred whole-day values.
    Unknown life stages and scopes leave the keeper with manual scheduling.
    """
    if (
        guide is None
        or guide.biological_group != animal_group
        or guide.scientific_name != scientific_name
    ):
        return ()
    claims = tuple(
        claim
        for claim in guide.claims
        if claim.fact_key in {"feeding_interval", "feeding_frequency"}
        and claim.scope == scientific_name
        and claim.life_stage
        and claim.context
        and claim.context.casefold().startswith("captive")
    )
    sources = {source.source_id: source for source in guide.sources}
    options = []
    for claim in claims:
        peers = tuple(
            c
            for c in claims
            if (c.life_stage, c.context, c.scope) == (claim.life_stage, claim.context, claim.scope)
        )
        support = support_state(peers, sources)
        value = claim.value_number
        interval = (
            int(value)
            if claim.fact_key == "feeding_interval"
            and claim.unit == "days"
            and value is not None
            and value.is_integer()
            and 1 <= value <= 3650
            else None
        )
        options.append(FeedingOption(claim, sources[claim.source_id], interval, support))
    return tuple(options)


class PreviewValidationError(ValueError):
    """A confirmation must be generated and used in the same authenticated session."""


class CarePreviewSigner:
    def __init__(self, secret: bytes) -> None:
        self._key = hmac.digest(secret, b"care-keeper:smart-care-preview:v1", "sha256")

    def sign(self, payload: dict[str, Any], *, session: str, now: datetime) -> str:
        body = json.dumps(
            {
                "payload": payload,
                "session": hashlib.sha256(session.encode()).hexdigest(),
                "expires": int(now.timestamp()) + 3600,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(body).decode()
        return encoded + "." + hmac.digest(self._key, encoded.encode(), "sha256").hex()

    def verify(self, token: str, *, session: str, now: datetime) -> dict[str, Any]:
        try:
            if len(token) > 40000:
                raise ValueError
            encoded, signature = token.rsplit(".", 1)
            expected = hmac.digest(self._key, encoded.encode(), "sha256").hex()
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            data = json.loads(base64.urlsafe_b64decode(encoded))
            if (
                data["session"] != hashlib.sha256(session.encode()).hexdigest()
                or data["expires"] <= now.timestamp()
                or not isinstance(data["payload"], dict)
            ):
                raise ValueError
            return dict(data["payload"])
        except (ValueError, KeyError, TypeError) as error:
            raise PreviewValidationError(
                "This preview is invalid or expired. Review the care setup again."
            ) from error
