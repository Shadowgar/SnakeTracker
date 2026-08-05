"""Request correlation context."""

from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import uuid4

correlation_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)
SAFE_CORRELATION_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def normalize_correlation_id(value: str | None) -> str:
    if value is not None and SAFE_CORRELATION_ID.fullmatch(value):
        return value
    return str(uuid4())
