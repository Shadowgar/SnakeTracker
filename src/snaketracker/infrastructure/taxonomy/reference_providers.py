"""Bounded, attribution-preserving providers for licensed species imagery."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from snaketracker.application.species_directory import (
    ProviderUnavailableError,
    ReferenceImageCandidate,
    TaxonRecord,
)

MAX_RESPONSE_BYTES = 1024 * 1024
USER_AGENT = "CareKeeper/0.1 licensed-species-images (https://github.com/paulrocco/SnakeTracker)"


class WikimediaCommonsImageProvider:
    """Find a verified free-culture image from Wikimedia Commons."""

    provider_name = "wikimedia_commons"

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        self._timeout_seconds = timeout_seconds

    def find(self, taxon: TaxonRecord) -> ReferenceImageCandidate | None:
        parameters = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": f'"{taxon.accepted_scientific_name}" filetype:bitmap',
            "gsrnamespace": "6",
            "gsrlimit": "12",
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": "1600",
            "origin": "*",
        }
        payload = _request_json(
            f"https://commons.wikimedia.org/w/api.php?{urlencode(parameters)}",
            self._timeout_seconds,
        )
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, list):
            return None
        expected = _normalize(taxon.accepted_scientific_name)
        for raw_page in pages:
            candidate = _commons_candidate(raw_page, expected)
            if candidate is not None:
                return candidate
        return None


class GBIFImageProvider:
    """Find a commercial-use occurrence image through GBIF's bounded cache."""

    provider_name = "gbif"

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        self._timeout_seconds = timeout_seconds

    def find(self, taxon: TaxonRecord) -> ReferenceImageCandidate | None:
        match = _request_json(
            "https://api.gbif.org/v1/species/match?"
            + urlencode(
                {
                    "name": taxon.accepted_scientific_name,
                    "kingdom": taxon.kingdom or "Animalia",
                }
            ),
            self._timeout_seconds,
        )
        usage_key = match.get("usageKey")
        scientific_name = _string(match.get("scientificName"), 256)
        if (
            type(usage_key) is not int
            or usage_key <= 0
            or match.get("matchType") == "NONE"
            or scientific_name is None
            or not _same_taxon(scientific_name, taxon.accepted_scientific_name)
        ):
            return None
        payload = _request_json(
            "https://api.gbif.org/v1/occurrence/search?"
            + urlencode(
                {
                    "taxon_key": str(usage_key),
                    "media_type": "StillImage",
                    "limit": "50",
                }
            ),
            self._timeout_seconds,
        )
        results = payload.get("results")
        if not isinstance(results, list):
            return None
        for raw_record in results:
            candidate = _gbif_candidate(raw_record)
            if candidate is not None:
                return candidate
        return None


def _commons_candidate(raw: object, expected: str) -> ReferenceImageCandidate | None:
    if not isinstance(raw, dict):
        return None
    page = cast(dict[str, Any], raw)
    page_id = page.get("pageid")
    title = _string(page.get("title"), 512)
    image_info = page.get("imageinfo")
    if (
        type(page_id) is not int
        or title is None
        or not isinstance(image_info, list)
        or not image_info
    ):
        return None
    info = image_info[0]
    if not isinstance(info, dict) or info.get("mime") not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        return None
    metadata = info.get("extmetadata")
    if not isinstance(metadata, dict):
        return None
    description = _metadata_text(metadata, "ImageDescription", 2048) or ""
    if expected not in _normalize(f"{title} {description}"):
        return None
    creator = _metadata_text(metadata, "Artist", 256)
    license_name = _metadata_text(metadata, "LicenseShortName", 64)
    license_url_raw = _metadata_text(metadata, "LicenseUrl", 1024)
    license_data = _license(license_name, license_url_raw)
    download_url = _string(info.get("thumburl") or info.get("url"), 2048)
    if creator is None or license_data is None or download_url is None:
        return None
    source_page_url = "https://commons.wikimedia.org/wiki/" + quote(
        title.replace(" ", "_"), safe=":()_-"
    )
    return ReferenceImageCandidate(
        provider="wikimedia_commons",
        provider_record_id=str(page_id),
        download_url=download_url,
        source_page_url=source_page_url,
        creator=creator,
        attribution=f"{creator} · Wikimedia Commons",
        license_code=license_data[0],
        license_url=license_data[1],
        retrieved_at=datetime.now(UTC),
    )


def _gbif_candidate(raw: object) -> ReferenceImageCandidate | None:
    if not isinstance(raw, dict):
        return None
    record = cast(dict[str, Any], raw)
    occurrence_key = record.get("key")
    media = record.get("media")
    if type(occurrence_key) is not int or not isinstance(media, list):
        return None
    for index, raw_media in enumerate(media):
        if not isinstance(raw_media, dict) or raw_media.get("type") != "StillImage":
            continue
        item = cast(dict[str, Any], raw_media)
        identifier = _string(item.get("identifier"), 2048)
        creator = _string(item.get("creator"), 256)
        license_data = _license(
            _string(item.get("license"), 256), _string(item.get("license"), 1024)
        )
        if identifier is None or creator is None or license_data is None:
            continue
        digest = hashlib.md5(identifier.encode(), usedforsecurity=False).hexdigest()
        source_page_url = (
            _https_url(item.get("references"))
            or f"https://www.gbif.org/occurrence/{occurrence_key}"
        )
        return ReferenceImageCandidate(
            provider="gbif",
            provider_record_id=f"{occurrence_key}:{index}:{digest}",
            download_url=(
                "https://api.gbif.org/v1/image/cache/1200x/occurrence/"
                f"{occurrence_key}/media/{digest}"
            ),
            source_page_url=source_page_url,
            creator=creator,
            attribution=f"{creator} · GBIF occurrence {occurrence_key}",
            license_code=license_data[0],
            license_url=license_data[1],
            retrieved_at=datetime.now(UTC),
        )
    return None


def _request_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ProviderUnavailableError("Reference image provider lookup failed.") from error
    if content_type != "application/json" or len(body) > MAX_RESPONSE_BYTES:
        raise ProviderUnavailableError("Reference image provider returned an invalid response.")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderUnavailableError(
            "Reference image provider returned malformed JSON."
        ) from error
    if not isinstance(payload, dict):
        raise ProviderUnavailableError("Reference image provider response schema is invalid.")
    return cast(dict[str, Any], payload)


def _metadata_text(metadata: dict[str, Any], key: str, maximum: int) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, dict):
        return None
    return _plain_text(value.get("value"), maximum)


def _plain_text(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return _string(html.unescape(re.sub(r"<[^>]+>", " ", value)), maximum)


def _license(name: str | None, url: str | None) -> tuple[str, str] | None:
    value = f"{name or ''} {url or ''}".casefold()
    if "-nd" in value or "/by-nd/" in value or "/by-nc-nd/" in value:
        return None
    if "public domain" in value or "cc0" in value or "/zero/" in value:
        return "cc0", "https://creativecommons.org/publicdomain/zero/1.0/"
    if "by-nc-sa" in value or "/by-nc-sa/" in value:
        return "cc-by-nc-sa", _creative_commons_url(url, "by-nc-sa")
    if "by-nc" in value or "/by-nc/" in value or "noncommercial" in value:
        return "cc-by-nc", _creative_commons_url(url, "by-nc")
    if "by-sa" in value or "/by-sa/" in value:
        return "cc-by-sa", _creative_commons_url(url, "by-sa")
    if "cc by" in value or "/by/" in value:
        return "cc-by", _creative_commons_url(url, "by")
    return None


def _creative_commons_url(value: str | None, kind: str) -> str:
    if value is not None and value.startswith("https://creativecommons.org/"):
        return value
    return f"https://creativecommons.org/licenses/{kind}/4.0/"


def _same_taxon(left: str, right: str) -> bool:
    expected = _normalize(right)
    return _normalize(left).startswith(expected)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _string(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    return normalized if normalized and len(normalized) <= maximum else None


def _https_url(value: object) -> str | None:
    text = _string(value, 2048)
    return text if text is not None and text.startswith("https://") else None
