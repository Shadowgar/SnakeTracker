from __future__ import annotations

import json
import logging

from snaketracker.infrastructure.observability.correlation import correlation_context
from snaketracker.infrastructure.observability.logging import JsonFormatter, configure_logging


def test_json_logging_includes_safe_context_and_correlation() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="snaketracker.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="startup complete",
        args=(),
        exc_info=None,
    )
    record.context = {"component": "web", "runtime_secret": "do-not-log"}
    token = correlation_context.set("request-123")
    try:
        payload = json.loads(formatter.format(record))
    finally:
        correlation_context.reset(token)

    assert payload["message"] == "startup complete"
    assert payload["correlation_id"] == "request-123"
    assert payload["context"] == {"component": "web", "runtime_secret": "[REDACTED]"}
    assert "do-not-log" not in json.dumps(payload)


def test_exception_logging_does_not_render_exception_text() -> None:
    formatter = JsonFormatter()
    try:
        raise RuntimeError("secret exception detail")
    except RuntimeError:
        record = logging.LogRecord(
            name="snaketracker.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=35,
            msg="request failed",
            args=(),
            exc_info=__import__("sys").exc_info(),
        )

    rendered = formatter.format(record)

    assert "secret exception detail" not in rendered
    assert json.loads(rendered)["exception"] == "Internal error"


def test_logging_configuration_installs_json_handler() -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging("warning")

        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
