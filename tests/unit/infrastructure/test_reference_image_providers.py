from __future__ import annotations

import json
from datetime import UTC, datetime
from email.message import Message
from typing import Self
from urllib.error import URLError
from urllib.request import Request
from uuid import uuid4

import pytest

from snaketracker.application.species_directory import TaxonRecord
from snaketracker.infrastructure.taxonomy import reference_providers
from snaketracker.infrastructure.taxonomy.reference_providers import (
    GBIFImageProvider,
    WikimediaCommonsImageProvider,
)


class Response:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode()
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return self.body


def _taxon(scientific_name: str = "Boa constrictor") -> TaxonRecord:
    now = datetime.now(UTC)
    return TaxonRecord(
        taxon_id=uuid4(),
        supported_group="snake",
        accepted_scientific_name=scientific_name,
        preferred_common_name="Boa Constrictor",
        authorship=None,
        alternative_common_names=(),
        synonyms=(),
        taxonomic_status="accepted",
        rank="species",
        kingdom="Animalia",
        phylum_division=None,
        class_name=None,
        order_name=None,
        family="Boidae",
        genus="Boa",
        species=scientific_name,
        infra_rank=None,
        provider="inaturalist",
        provider_id="1",
        source_url="https://www.inaturalist.org/taxa/1",
        retrieved_at=now,
        refreshed_at=now,
        stale=False,
    )


def test_commons_retains_attribution_and_allows_noncommercial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 0,
                    "title": "File:Boa constrictor no derivatives.jpg",
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/no-derivatives.jpg",
                            "extmetadata": {
                                "ImageDescription": {"value": "Boa constrictor"},
                                "Artist": {"value": "ND creator"},
                                "LicenseShortName": {"value": "CC BY-NC-ND 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-nc-nd/4.0/"
                                },
                            },
                        }
                    ],
                },
                {
                    "pageid": 1,
                    "title": "File:Boa constrictor restricted.jpg",
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/restricted.jpg",
                            "extmetadata": {
                                "ImageDescription": {"value": "Boa constrictor"},
                                "Artist": {"value": "Restricted creator"},
                                "LicenseShortName": {"value": "CC BY-NC 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-nc/4.0/"
                                },
                            },
                        }
                    ],
                },
                {
                    "pageid": 2,
                    "title": "File:Boa constrictor.jpg",
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/boa.jpg",
                            "extmetadata": {
                                "ImageDescription": {"value": "<i>Boa constrictor</i>"},
                                "Artist": {"value": "<a>Licensed Creator</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                                },
                            },
                        }
                    ],
                },
            ]
        }
    }
    monkeypatch.setattr(
        reference_providers,
        "urlopen",
        lambda *_args, **_kwargs: Response(payload),
    )

    candidate = WikimediaCommonsImageProvider().find(_taxon())

    assert candidate is not None
    assert candidate.provider == "wikimedia_commons"
    assert candidate.provider_record_id == "1"
    assert candidate.creator == "Restricted creator"
    assert candidate.license_code == "cc-by-nc"
    assert candidate.source_page_url.endswith("File:Boa_constrictor_restricted.jpg")


def test_gbif_uses_fixed_cache_origin_and_commercial_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def open_fixture(request: Request, *, timeout: float) -> Response:
        calls.append(request.full_url)
        assert timeout == 3.0
        if "/species/match" in request.full_url:
            return Response(
                {
                    "usageKey": 2464899,
                    "matchType": "EXACT",
                    "scientificName": "Boa constrictor Linnaeus, 1758",
                }
            )
        return Response(
            {
                "results": [
                    {
                        "key": 42,
                        "media": [
                            {
                                "type": "StillImage",
                                "identifier": "https://publisher.example/boa.jpg",
                                "creator": "Occurrence Creator",
                                "license": "https://creativecommons.org/licenses/by/4.0/",
                                "references": "https://www.gbif.org/occurrence/42",
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(reference_providers, "urlopen", open_fixture)

    candidate = GBIFImageProvider().find(_taxon())

    assert candidate is not None
    assert candidate.download_url.startswith("https://api.gbif.org/v1/image/cache/1200x/")
    assert candidate.creator == "Occurrence Creator"
    assert candidate.license_code == "cc-by"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("name", "url", "expected"),
    [
        ("CC BY-NC-ND 4.0", None, None),
        ("Public domain", None, "cc0"),
        ("CC BY-NC-SA 4.0", None, "cc-by-nc-sa"),
        ("NonCommercial", None, "cc-by-nc"),
        ("CC BY-SA 4.0", None, "cc-by-sa"),
        ("CC BY 4.0", None, "cc-by"),
        ("All Rights Reserved", None, None),
    ],
)
def test_license_normalization_covers_allowed_and_rejected_terms(
    name: str, url: str | None, expected: str | None
) -> None:
    result = reference_providers._license(name, url)
    assert (result[0] if result else None) == expected


def test_provider_helpers_reject_invalid_values_and_preserve_cc_url() -> None:
    assert reference_providers._string(None, 4) is None
    assert reference_providers._string("   ", 4) is None
    assert reference_providers._string("abcde", 4) is None
    assert reference_providers._https_url("http://example.test") is None
    assert reference_providers._https_url("https://example.test") == "https://example.test"
    license_url = "https://creativecommons.org/licenses/by/3.0/"
    assert reference_providers._creative_commons_url(license_url, "by") == license_url


def test_commons_and_gbif_treat_malformed_provider_shapes_as_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            Response({"query": {"pages": [None, {"pageid": "bad"}]}}),
            Response({"usageKey": 1, "matchType": "NONE", "scientificName": "Boa constrictor"}),
        ]
    )
    monkeypatch.setattr(reference_providers, "urlopen", lambda *_args, **_kwargs: next(responses))

    assert WikimediaCommonsImageProvider().find(_taxon()) is None
    assert GBIFImageProvider().find(_taxon()) is None


def test_gbif_skips_invalid_media_and_uses_occurrence_page_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            Response(
                {
                    "usageKey": 1,
                    "matchType": "EXACT",
                    "scientificName": "Boa constrictor",
                }
            ),
            Response(
                {
                    "results": [
                        None,
                        {"key": "bad", "media": []},
                        {
                            "key": 7,
                            "media": [
                                None,
                                {"type": "Sound"},
                                {
                                    "type": "StillImage",
                                    "identifier": "https://publisher.example/boa.jpg",
                                    "creator": "Creator",
                                    "license": "CC BY-NC-SA 4.0",
                                    "references": "http://not-accepted.example",
                                },
                            ],
                        },
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(reference_providers, "urlopen", lambda *_args, **_kwargs: next(responses))

    candidate = GBIFImageProvider().find(_taxon())
    assert candidate is not None
    assert candidate.license_code == "cc-by-nc-sa"
    assert candidate.source_page_url == "https://www.gbif.org/occurrence/7"


def test_request_json_maps_transport_and_response_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reference_providers,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(reference_providers.ProviderUnavailableError):
        reference_providers._request_json("https://example.test", 1.0)


def test_providers_reject_missing_collections_and_exhaust_empty_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            Response({}),
            Response(
                {
                    "usageKey": 1,
                    "matchType": "EXACT",
                    "scientificName": "Boa constrictor",
                }
            ),
            Response({}),
            Response(
                {
                    "usageKey": 1,
                    "matchType": "EXACT",
                    "scientificName": "Boa constrictor",
                }
            ),
            Response({"results": []}),
        ]
    )
    monkeypatch.setattr(reference_providers, "urlopen", lambda *_args, **_kwargs: next(responses))

    assert WikimediaCommonsImageProvider().find(_taxon()) is None
    assert GBIFImageProvider().find(_taxon()) is None
    assert GBIFImageProvider().find(_taxon()) is None


def test_candidate_helpers_reject_invalid_image_metadata() -> None:
    expected = reference_providers._normalize("Boa constrictor")
    assert (
        reference_providers._commons_candidate(
            {
                "pageid": 1,
                "title": "File:Boa constrictor.svg",
                "imageinfo": [{"mime": "image/svg+xml"}],
            },
            expected,
        )
        is None
    )
    assert (
        reference_providers._commons_candidate(
            {
                "pageid": 1,
                "title": "File:Boa constrictor.jpg",
                "imageinfo": [{"mime": "image/jpeg", "extmetadata": []}],
            },
            expected,
        )
        is None
    )
    assert reference_providers._gbif_candidate({"key": 1, "media": []}) is None
    assert (
        reference_providers._gbif_candidate(
            {
                "key": 1,
                "media": [
                    {
                        "type": "StillImage",
                        "identifier": "https://example.test/image.jpg",
                        "creator": "",
                        "license": "CC BY 4.0",
                    }
                ],
            }
        )
        is None
    )
    assert reference_providers._plain_text(None, 10) is None


def test_request_json_rejects_wrong_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Response({})
    response.headers.replace_header("Content-Type", "text/html")
    monkeypatch.setattr(reference_providers, "urlopen", lambda *_args, **_kwargs: response)
    with pytest.raises(reference_providers.ProviderUnavailableError):
        reference_providers._request_json("https://example.test", 1.0)

    invalid = Response([])
    monkeypatch.setattr(reference_providers, "urlopen", lambda *_args, **_kwargs: invalid)
    with pytest.raises(reference_providers.ProviderUnavailableError):
        reference_providers._request_json("https://example.test", 1.0)
