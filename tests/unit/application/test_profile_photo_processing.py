from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from snaketracker.application.attachments import (
    MAX_PROFILE_PHOTO_BYTES,
    MAX_PROFILE_PHOTO_LONG_EDGE,
    AttachmentValidationError,
    _process_profile_photo,
)


def _encoded_image(
    image_format: str,
    *,
    size: tuple[int, int] = (320, 240),
    exif: Image.Exif | None = None,
) -> bytes:
    image = Image.new("RGB", size, "#6f8f62")
    output = BytesIO()
    save_options = {"exif": exif} if exif is not None else {}
    image.save(output, format=image_format, **save_options)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "media_type"),
    (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")),
)
def test_safe_raster_formats_are_content_validated_and_canonicalized(
    image_format: str, media_type: str
) -> None:
    processed = _process_profile_photo(_encoded_image(image_format), media_type)

    assert processed.metadata.media_type == media_type
    assert processed.metadata.size_bytes == len(processed.content)
    with Image.open(BytesIO(processed.content)) as derivative:
        assert derivative.format == image_format
        assert derivative.size == (320, 240)
        assert not derivative.getexif()


def test_phone_scale_jpeg_is_downsized_and_raw_metadata_is_not_retained() -> None:
    source = Image.effect_noise((3072, 4080), 65).convert("RGB")
    exif = Image.Exif()
    exif[274] = 6
    exif[271] = "Motorola"
    exif[272] = "Moto G 5G (2024)"
    exif[306] = "2026:09:01 12:00:00"
    exif[34853] = {
        1: "N",
        2: (IFDRational(40), IFDRational(0), IFDRational(0)),
        3: "W",
        4: (IFDRational(74), IFDRational(0), IFDRational(0)),
    }
    encoded = BytesIO()
    source.save(encoded, format="JPEG", quality=70, exif=exif)
    source.close()
    upload = encoded.getvalue()

    assert 5 * 1024 * 1024 < len(upload) < MAX_PROFILE_PHOTO_BYTES
    processed = _process_profile_photo(upload, "image/jpeg")

    assert max(processed.metadata.width, processed.metadata.height) == (MAX_PROFILE_PHOTO_LONG_EDGE)
    assert processed.metadata.width > processed.metadata.height
    assert len(processed.content) < len(upload)
    with Image.open(BytesIO(processed.content)) as derivative:
        assert derivative.size == (
            processed.metadata.width,
            processed.metadata.height,
        )
        assert not derivative.getexif()
        assert "exif" not in derivative.info


def test_invalid_mismatched_heif_and_pathological_images_have_distinct_errors() -> None:
    jpeg = _encoded_image("JPEG")
    with pytest.raises(AttachmentValidationError, match="does not match"):
        _process_profile_photo(jpeg, "image/png")
    with pytest.raises(AttachmentValidationError, match="damaged"):
        _process_profile_photo(b"not an image", "image/jpeg")
    with pytest.raises(AttachmentValidationError, match="HEIC/HEIF"):
        _process_profile_photo(b"\0\0\0\x18ftypheic" + b"\0" * 32, "image/heic")
    with pytest.raises(AttachmentValidationError, match="20 MiB"):
        _process_profile_photo(b"x" * (MAX_PROFILE_PHOTO_BYTES + 1), "image/jpeg")

    oversized = BytesIO()
    Image.new("1", (8193, 1)).save(oversized, format="PNG")
    with pytest.raises(AttachmentValidationError, match="8192-pixel"):
        _process_profile_photo(oversized.getvalue(), "image/png")

    excessive_pixels = BytesIO()
    Image.new("1", (6000, 5000)).save(excessive_pixels, format="PNG")
    with pytest.raises(AttachmentValidationError, match="25-megapixel"):
        _process_profile_photo(excessive_pixels.getvalue(), "image/png")
