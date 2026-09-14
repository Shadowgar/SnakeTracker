"""Bounded local cache for licensed global taxon reference images."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from snaketracker.application.species_directory import (
    CachedReferenceImage,
    ProviderUnavailableError,
)

MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_REFERENCE_IMAGE_PIXELS = 25_000_000
MAX_REFERENCE_IMAGE_DIMENSION = 8_192
ALLOWED_REFERENCE_IMAGE_HOSTS = frozenset(
    {"static.inaturalist.org", "inaturalist-open-data.s3.amazonaws.com"}
)
ALLOWED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


FetchReferenceImage = Callable[[Request, float], tuple[str, bytes]]


class LocalReferenceImageCache:
    """Fetch approved origins server-side and persist normalized WebP bytes locally."""

    def __init__(
        self,
        root: Path,
        *,
        timeout_seconds: float = 3.0,
        fetch: FetchReferenceImage | None = None,
    ) -> None:
        self._root = root
        self._timeout_seconds = timeout_seconds
        self._fetch = fetch or self._fetch_remote

    def cache(self, taxon_id: UUID, source_url: str) -> CachedReferenceImage:
        _validate_source_url(source_url)
        request = Request(
            source_url,
            headers={
                "Accept": "image/jpeg,image/png,image/webp",
                "User-Agent": "CareKeeper/0.1 licensed-reference-image-cache",
            },
            method="GET",
        )
        try:
            content_type, source = self._fetch(request, self._timeout_seconds)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailableError("Reference image download failed.") from error
        if content_type.lower().split(";", 1)[0].strip() not in ALLOWED_MEDIA_TYPES:
            raise ProviderUnavailableError("Reference image media type is not permitted.")
        if not source or len(source) > MAX_REFERENCE_IMAGE_BYTES:
            raise ProviderUnavailableError("Reference image exceeds the safe size limit.")
        normalized = _normalize_image(source)
        filename = f"{taxon_id}.webp"
        self._root.mkdir(parents=True, exist_ok=True, mode=0o750)
        destination = self._root / filename
        temporary = self._root / f".{filename}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(normalized)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o640)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return CachedReferenceImage(
            filename=filename,
            media_type="image/webp",
            byte_size=len(normalized),
            sha256=hashlib.sha256(normalized).hexdigest(),
            cached_at=datetime.now(UTC),
            content=normalized,
        )

    def load(self, filename: str, expected_sha256: str) -> bytes:
        if re.fullmatch(r"[0-9a-f-]{36}\.webp", filename) is None:
            raise ProviderUnavailableError("Reference image cache metadata is invalid.")
        path = (self._root / filename).resolve()
        if path.parent != self._root.resolve():
            raise ProviderUnavailableError("Reference image cache path is invalid.")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ProviderUnavailableError("Reference image cache entry is unavailable.") from error
        if not content or not hmac.compare_digest(
            hashlib.sha256(content).hexdigest(), expected_sha256
        ):
            raise ProviderUnavailableError("Reference image cache integrity check failed.")
        return content

    @staticmethod
    def _fetch_remote(request: Request, timeout: float) -> tuple[str, bytes]:
        opener = build_opener(_NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            content = response.read(MAX_REFERENCE_IMAGE_BYTES + 1)
        return content_type, content


def _validate_source_url(source_url: str) -> None:
    parsed = urlsplit(source_url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ProviderUnavailableError("Reference image origin is not permitted.") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_REFERENCE_IMAGE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ProviderUnavailableError("Reference image origin is not permitted.")


def _normalize_image(source: bytes) -> bytes:
    try:
        with Image.open(BytesIO(source)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ProviderUnavailableError("Reference image format is not permitted.")
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width > MAX_REFERENCE_IMAGE_DIMENSION
                or height > MAX_REFERENCE_IMAGE_DIMENSION
                or width * height > MAX_REFERENCE_IMAGE_PIXELS
            ):
                raise ProviderUnavailableError("Reference image exceeds the safe dimension limit.")
            image.load()
            normalized = image.convert("RGB")
            normalized.thumbnail((1_600, 1_600), Image.Resampling.LANCZOS)
            output = BytesIO()
            normalized.save(output, format="WEBP", quality=82, method=4)
            normalized.close()
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ProviderUnavailableError("Reference image is not a valid image.") from error
