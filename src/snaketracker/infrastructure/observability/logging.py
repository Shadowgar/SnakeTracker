"""Structured redacted logging."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

from snaketracker.infrastructure.observability.correlation import correlation_context

SENSITIVE_KEY_PARTS = ("authorization", "cookie", "password", "secret", "token")


def _redact_context(context: object) -> dict[str, object]:
    if not isinstance(context, Mapping):
        return {}
    safe: dict[str, object] = {}
    for raw_key, value in context.items():
        key = str(raw_key)
        safe[key] = (
            "[REDACTED]" if any(part in key.lower() for part in SENSITIVE_KEY_PARTS) else value
        )
    return safe


class JsonFormatter(logging.Formatter):
    """Render a stable JSON log envelope without exception details."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = correlation_context.get()
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        context = _redact_context(getattr(record, "context", None))
        if context:
            payload["context"] = context
        if record.exc_info is not None:
            payload["exception"] = "Internal error"
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    """Configure the root logger once at the composition boundary."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
