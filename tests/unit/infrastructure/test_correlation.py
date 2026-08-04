from __future__ import annotations

from uuid import UUID

from snaketracker.infrastructure.observability.correlation import normalize_correlation_id


def test_safe_correlation_id_is_preserved() -> None:
    assert normalize_correlation_id("request-123.example") == "request-123.example"


def test_invalid_correlation_id_is_replaced_with_uuid() -> None:
    generated = normalize_correlation_id("unsafe value with spaces")

    assert str(UUID(generated)) == generated
