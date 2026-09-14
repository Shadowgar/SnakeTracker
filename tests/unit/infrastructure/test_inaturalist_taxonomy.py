from __future__ import annotations

import json
from email.message import Message
from typing import Self
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from snaketracker.application.species_directory import ProviderUnavailableError
from snaketracker.infrastructure.taxonomy import inaturalist
from snaketracker.infrastructure.taxonomy.inaturalist import (
    MAX_RESPONSE_BYTES,
    INaturalistTaxonomyProvider,
)


class Response:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return self.body


def test_provider_normalizes_filters_and_sends_only_taxonomy_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_url = ""
    payload = {
        "results": [
            {
                "id": 32158,
                "name": "Python regius",
                "rank": "species",
                "preferred_common_name": "Ball Python",
                "matched_term": "Royal Python",
                "ancestor_ids": [1, 355675, 85553],
                "default_photo": {
                    "medium_url": "https://static.inaturalist.org/photo.jpg",
                    "attribution": "A Keeper, CC BY",
                    "license_code": "cc-by",
                },
            },
            {
                "id": 69223,
                "name": "Epipremnum aureum",
                "rank": "species",
                "preferred_common_name": "Golden Pothos",
                "ancestor_ids": [47126],
            },
        ]
    }

    def open_fixture(request: Request, *, timeout: float) -> Response:
        nonlocal seen_url
        seen_url = request.full_url
        assert timeout == 3.0
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(inaturalist, "urlopen", open_fixture)
    results = INaturalistTaxonomyProvider().search("ball p", "snake", limit=5)

    assert len(results) == 1
    assert results[0].preferred_common_name == "Ball Python"
    assert results[0].synonyms == ("Royal Python",)
    assert results[0].image_license_code == "cc-by"
    assert "q=ball+p" in seen_url
    assert "household" not in seen_url and "animal" not in seen_url


def test_provider_ignores_malformed_rows_and_stops_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = {
        "id": 32158,
        "name": "Python regius",
        "rank": "species",
        "preferred_common_name": "Ball Python",
        "ancestor_ids": [85553],
    }
    payload = {"results": ["not-a-record", valid, {**valid, "id": 32159}]}
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    results = INaturalistTaxonomyProvider().search("python", "snake", limit=1)

    assert len(results) == 1
    assert results[0].provider_id == "32158"


def test_provider_accepts_noncommercial_photo_and_retains_photo_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "results": [
            {
                "id": 32093,
                "name": "Boa constrictor",
                "rank": "species",
                "preferred_common_name": "Boa Constrictor",
                "ancestor_ids": [85553],
                "default_photo": {
                    "id": 588689904,
                    "medium_url": "https://static.inaturalist.org/photos/588689904/medium.jpg",
                    "attribution": "Owner supplied creator, CC BY-NC",
                    "attribution_name": "Owner supplied creator",
                    "license_code": "cc-by-nc",
                },
            }
        ]
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    result = INaturalistTaxonomyProvider().search("boa constrictor", "snake", limit=5)[0]

    assert result.image_license_code == "cc-by-nc"
    assert result.image_provider_record_id == "588689904"
    assert result.image_source_page_url == "https://www.inaturalist.org/photos/588689904"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (Response(b"not-json"), "malformed JSON"),
        (Response(b"[]"), "schema is invalid"),
        (Response(b"{}", "text/html"), "invalid response"),
        (Response(b"x" * (MAX_RESPONSE_BYTES + 1)), "invalid response"),
    ],
)
def test_provider_rejects_malformed_oversized_and_wrong_content(
    monkeypatch: pytest.MonkeyPatch, response: Response, expected: str
) -> None:
    monkeypatch.setattr(inaturalist, "urlopen", lambda *_args, **_kwargs: response)
    with pytest.raises(ProviderUnavailableError, match=expected):
        INaturalistTaxonomyProvider().search("python", "snake", limit=5)


def test_provider_timeout_becomes_normal_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(inaturalist, "urlopen", timeout)
    with pytest.raises(ProviderUnavailableError, match="lookup failed"):
        INaturalistTaxonomyProvider().search("python", "snake", limit=5)


def test_provider_rate_limit_becomes_normal_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rate_limited(*_args: object, **_kwargs: object) -> None:
        raise HTTPError("https://api.inaturalist.org", 429, "limited", Message(), None)

    monkeypatch.setattr(inaturalist, "urlopen", rate_limited)
    with pytest.raises(ProviderUnavailableError, match="lookup failed"):
        INaturalistTaxonomyProvider().search("python", "snake", limit=5)


def test_provider_detail_adds_named_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "id": 32158,
                "name": "Python regius",
                "rank": "species",
                "preferred_common_name": "Ball Python",
                "ancestor_ids": [1, 355675, 85553],
                "ancestors": [
                    {"rank": "kingdom", "name": "Animalia"},
                    {"rank": "phylum", "name": "Chordata"},
                    {"rank": "class", "name": "Reptilia"},
                    {"rank": "order", "name": "Squamata"},
                    {"rank": "family", "name": "Pythonidae"},
                ],
            }
        ]
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )
    detail = INaturalistTaxonomyProvider().detail("32158", "snake")
    assert (detail.phylum_division, detail.class_name, detail.order_name, detail.family) == (
        "Chordata",
        "Reptilia",
        "Squamata",
        "Pythonidae",
    )


def test_provider_detail_rejects_identifier_schema_and_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = INaturalistTaxonomyProvider()
    with pytest.raises(ProviderUnavailableError, match="identifier"):
        provider.detail("not-an-id", "snake")

    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps({"results": []}).encode()),
    )
    with pytest.raises(ProviderUnavailableError, match="detail response schema"):
        provider.detail("32158", "snake")

    wrong_group = {
        "results": [
            {
                "id": 69223,
                "name": "Epipremnum aureum",
                "rank": "species",
                "ancestor_ids": [47126],
            }
        ]
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(wrong_group).encode()),
    )
    with pytest.raises(ProviderUnavailableError, match="selected group"):
        provider.detail("69223", "snake")


def test_provider_detail_rejects_malformed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inaturalist, "urlopen", lambda *_args, **_kwargs: Response(b"bad"))
    with pytest.raises(ProviderUnavailableError, match="malformed JSON"):
        INaturalistTaxonomyProvider().detail("32158", "snake")


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (Response(b"{}", "text/html"), "invalid response"),
        (Response(b"[]"), "schema is invalid"),
    ],
)
def test_provider_detail_rejects_invalid_transport_and_top_level_schema(
    monkeypatch: pytest.MonkeyPatch, response: Response, expected: str
) -> None:
    monkeypatch.setattr(inaturalist, "urlopen", lambda *_args, **_kwargs: response)
    with pytest.raises(ProviderUnavailableError, match=expected):
        INaturalistTaxonomyProvider().detail("32158", "snake")


@pytest.mark.parametrize("ancestors", ["invalid", ["invalid", {"rank": "family"}]])
def test_provider_detail_ignores_invalid_optional_classification_and_image(
    monkeypatch: pytest.MonkeyPatch, ancestors: object
) -> None:
    payload = {
        "results": [
            {
                "id": 32158,
                "name": "Python regius",
                "rank": "species",
                "ancestor_ids": [85553],
                "ancestors": ancestors,
                "default_photo": {
                    "medium_url": "http://unsafe.example.test/photo.jpg",
                    "attribution": "Unknown",
                    "license_code": "all-rights-reserved",
                },
            }
        ]
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    detail = INaturalistTaxonomyProvider().detail("32158", "snake")

    assert detail.family is None
    assert detail.image_source_url is None


def test_provider_accepts_noncommercial_reference_photo_without_optional_photo_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "results": [
            {
                "id": 32093,
                "name": "Boa constrictor",
                "rank": "species",
                "preferred_common_name": "Boa Constrictor",
                "ancestor_ids": [85553],
                "default_photo": {
                    "medium_url": (
                        "https://inaturalist-open-data.s3.amazonaws.com/photos/588689904/medium.jpg"
                    ),
                    "attribution": "Nicolas Burnel, some rights reserved (CC BY-NC)",
                    "attribution_name": "Nicolas Burnel",
                    "license_code": "cc-by-nc",
                },
            }
        ]
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    detail = INaturalistTaxonomyProvider().detail("32093", "snake")

    assert detail.image_source_url is not None
    assert detail.image_creator == "Nicolas Burnel"
    assert detail.image_license_code == "cc-by-nc"
    assert detail.image_provider_record_id is None
