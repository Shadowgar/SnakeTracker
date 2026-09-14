"""Bounded iNaturalist taxon-discovery adapter."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snaketracker.application.species_directory import ProviderTaxon, ProviderUnavailableError

API_ORIGIN = "https://api.inaturalist.org"
MAX_RESPONSE_BYTES = 256 * 1024
ANCESTOR_BY_GROUP = {
    "snake": 85553,
    "lizard": 85552,
    "spider": 47118,
    "scorpion": 48894,
    "plant": 47126,
}
IMAGE_LICENSES = frozenset({"cc0", "cc-by", "cc-by-sa"})


class INaturalistTaxonomyProvider:
    """Use public autocomplete without exposing any household context."""

    provider_name = "inaturalist"

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        self._timeout_seconds = timeout_seconds

    def search(self, query: str, group: str, *, limit: int) -> tuple[ProviderTaxon, ...]:
        ancestor_id = ANCESTOR_BY_GROUP[group]
        parameters = {
            "q": query,
            "rank": "species,subspecies",
            "per_page": min(limit * 2, 20),
        }
        url = f"{API_ORIGIN}/v1/taxa/autocomplete?{urlencode(parameters)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "CareKeeper/0.1 taxonomy-directory (https://github.com/paulrocco/SnakeTracker)",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailableError("iNaturalist lookup failed.") from error
        if content_type != "application/json" or len(body) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailableError("iNaturalist returned an invalid response.")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderUnavailableError("iNaturalist returned malformed JSON.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ProviderUnavailableError("iNaturalist response schema is invalid.")
        records: list[ProviderTaxon] = []
        for raw in cast(list[object], payload["results"]):
            parsed = _parse_taxon(raw, group, ancestor_id)
            if parsed is not None:
                records.append(parsed)
            if len(records) >= limit:
                break
        return tuple(records)

    def detail(self, provider_id: str, group: str) -> ProviderTaxon:
        if not provider_id.isdigit() or len(provider_id) > 20:
            raise ProviderUnavailableError("iNaturalist taxon identifier is invalid.")
        payload = self._request_json(f"{API_ORIGIN}/v1/taxa/{provider_id}")
        results = payload.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise ProviderUnavailableError("iNaturalist detail response schema is invalid.")
        parsed = _parse_detail(results[0], group, ANCESTOR_BY_GROUP[group])
        if parsed is None:
            raise ProviderUnavailableError("iNaturalist detail does not match the selected group.")
        return parsed

    def _request_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "CareKeeper/0.1 taxonomy-directory (https://github.com/paulrocco/SnakeTracker)",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailableError("iNaturalist lookup failed.") from error
        if content_type != "application/json" or len(body) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailableError("iNaturalist returned an invalid response.")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderUnavailableError("iNaturalist returned malformed JSON.") from error
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("iNaturalist response schema is invalid.")
        return cast(dict[str, Any], payload)


def _parse_taxon(raw: object, group: str, ancestor_id: int) -> ProviderTaxon | None:
    if not isinstance(raw, dict):
        return None
    data = cast(dict[str, Any], raw)
    provider_id = data.get("id")
    name = _bounded_string(data.get("name"), 256)
    rank = _bounded_string(data.get("rank"), 32)
    ancestor_ids = data.get("ancestor_ids")
    if (
        type(provider_id) is not int
        or provider_id <= 0
        or name is None
        or rank not in {"species", "subspecies"}
        or not isinstance(ancestor_ids, list)
        or ancestor_id not in ancestor_ids
    ):
        return None
    common = _bounded_string(data.get("preferred_common_name"), 256)
    matched = _bounded_string(data.get("matched_term"), 256)
    synonyms = () if matched is None or matched in {name, common} else (matched,)
    image = _image_fields(data.get("default_photo"))
    genus = name.split(" ", 1)[0] if " " in name else None
    return ProviderTaxon(
        provider="inaturalist",
        provider_id=str(provider_id),
        source_url=f"https://www.inaturalist.org/taxa/{provider_id}",
        supported_group=group,
        accepted_scientific_name=name,
        preferred_common_name=common,
        synonyms=synonyms,
        taxonomic_status="accepted",
        rank=rank,
        kingdom="Plantae" if group == "plant" else "Animalia",
        genus=genus,
        species=name,
        image_source_url=image[0],
        image_creator=image[1],
        image_attribution=image[2],
        image_license_code=image[3],
        image_license_url=image[4],
    )


def _parse_detail(raw: object, group: str, ancestor_id: int) -> ProviderTaxon | None:
    base = _parse_taxon(raw, group, ancestor_id)
    if base is None or not isinstance(raw, dict):
        return None
    ancestors = raw.get("ancestors")
    classification: dict[str, str] = {}
    if isinstance(ancestors, list):
        for ancestor in ancestors:
            if not isinstance(ancestor, dict):
                continue
            rank = _bounded_string(ancestor.get("rank"), 32)
            name = _bounded_string(ancestor.get("name"), 256)
            if rank is not None and name is not None:
                classification[rank] = name
    return replace(
        base,
        kingdom=classification.get("kingdom") or base.kingdom,
        phylum_division=classification.get("phylum"),
        class_name=classification.get("class"),
        order_name=classification.get("order"),
        family=classification.get("family"),
    )


def _image_fields(
    photo: object,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    if not isinstance(photo, dict):
        return None, None, None, None, None
    data = cast(dict[str, Any], photo)
    code = _bounded_string(data.get("license_code"), 32)
    url = _bounded_string(data.get("medium_url"), 1024)
    attribution = _bounded_string(data.get("attribution"), 512)
    if (
        code not in IMAGE_LICENSES
        or url is None
        or not url.startswith("https://")
        or attribution is None
    ):
        return None, None, None, None, None
    creator = (
        _bounded_string(data.get("attribution_name"), 256)
        or _bounded_string(data.get("name"), 256)
        or attribution
    )
    license_url = {
        "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
        "cc-by": "https://creativecommons.org/licenses/by/4.0/",
        "cc-by-sa": "https://creativecommons.org/licenses/by-sa/4.0/",
    }[code]
    return url, creator, attribution, code, license_url


def _bounded_string(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    return normalized if normalized and len(normalized) <= maximum else None
