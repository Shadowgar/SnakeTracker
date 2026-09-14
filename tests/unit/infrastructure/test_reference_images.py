from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

import pytest
from PIL import Image

from snaketracker.application.species_directory import ProviderUnavailableError
from snaketracker.infrastructure.taxonomy import reference_images
from snaketracker.infrastructure.taxonomy.reference_images import (
    MAX_REFERENCE_IMAGE_BYTES,
    LocalReferenceImageCache,
)


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (80, 60), "green").save(output, format="PNG")
    return output.getvalue()


def test_reference_image_cache_normalizes_and_integrity_checks(tmp_path) -> None:
    calls: list[tuple[str, float]] = []

    def fetch(request: Request, timeout: float) -> tuple[str, bytes]:
        calls.append((request.full_url, timeout))
        return "image/png", _png()

    cache = LocalReferenceImageCache(tmp_path, fetch=fetch)
    cached = cache.cache(uuid4(), "https://static.inaturalist.org/photos/1/medium.jpg")

    assert calls == [("https://static.inaturalist.org/photos/1/medium.jpg", 3.0)]
    assert cached.media_type == "image/webp"
    assert cache.load(cached.filename, cached.sha256) == cached.content
    with pytest.raises(ProviderUnavailableError, match="integrity"):
        cache.load(cached.filename, "0" * 64)
    with pytest.raises(ProviderUnavailableError, match="metadata"):
        cache.load("../escape.webp", cached.sha256)


def test_reference_image_cache_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "cache"
    root.mkdir()
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"outside")
    filename = f"{uuid4()}.webp"
    (root / filename).symlink_to(outside)

    with pytest.raises(ProviderUnavailableError, match="path"):
        LocalReferenceImageCache(root).load(filename, "0" * 64)


def test_reference_image_default_fetch_is_bounded(monkeypatch, tmp_path) -> None:
    class Response:
        def __init__(self) -> None:
            self.headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, limit):
            assert limit == MAX_REFERENCE_IMAGE_BYTES + 1
            return _png()

    class Opener:
        def open(self, request, *, timeout):
            assert request.full_url.startswith("https://static.inaturalist.org/")
            assert timeout == 3.0
            return Response()

    monkeypatch.setattr(reference_images, "build_opener", lambda _handler: Opener())
    cached = LocalReferenceImageCache(tmp_path).cache(
        uuid4(), "https://static.inaturalist.org/photo.png"
    )
    assert cached.media_type == "image/webp"


@pytest.mark.parametrize(
    ("url", "fetch", "message"),
    [
        (
            "https://evil.example/photo.jpg",
            lambda _request, _timeout: ("image/jpeg", _png()),
            "origin",
        ),
        (
            "https://static.inaturalist.org:bad/photo.jpg",
            lambda _request, _timeout: ("image/jpeg", _png()),
            "origin",
        ),
        (
            "https://static.inaturalist.org/photo.jpg",
            lambda _request, _timeout: ("text/html", b"not an image"),
            "media type",
        ),
        (
            "https://static.inaturalist.org/photo.jpg",
            lambda _request, _timeout: ("image/jpeg", b"x" * (MAX_REFERENCE_IMAGE_BYTES + 1)),
            "size limit",
        ),
        (
            "https://static.inaturalist.org/photo.jpg",
            lambda _request, _timeout: ("image/jpeg", b"not an image"),
            "valid image",
        ),
        (
            "https://static.inaturalist.org/photo.jpg",
            lambda _request, _timeout: ("image/png", _encoded_image("GIF", (80, 60))),
            "format",
        ),
        (
            "https://static.inaturalist.org/photo.jpg",
            lambda _request, _timeout: ("image/png", _encoded_image("PNG", (8193, 1))),
            "dimension",
        ),
    ],
)
def test_reference_image_cache_rejects_unsafe_or_invalid_responses(
    tmp_path, url, fetch, message
) -> None:
    with pytest.raises(ProviderUnavailableError, match=message):
        LocalReferenceImageCache(tmp_path, fetch=fetch).cache(uuid4(), url)


def test_reference_image_timeout_and_redirect_fail_closed(tmp_path) -> None:
    def timeout(_request: Request, _seconds: float) -> tuple[str, bytes]:
        raise TimeoutError

    def redirect(request: Request, _seconds: float) -> tuple[str, bytes]:
        raise HTTPError(request.full_url, 302, "redirect", {}, None)

    for fetch in (timeout, redirect):
        with pytest.raises(ProviderUnavailableError, match="download failed"):
            LocalReferenceImageCache(tmp_path, fetch=fetch).cache(
                uuid4(), "https://static.inaturalist.org/photo.jpg"
            )


def _encoded_image(image_format: str, size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "green").save(output, format=image_format)
    return output.getvalue()
