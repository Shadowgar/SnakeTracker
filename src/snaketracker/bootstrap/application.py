"""FastAPI composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from snaketracker.application.ports.readiness import ReadinessPort
from snaketracker.infrastructure.observability.correlation import (
    correlation_context,
    normalize_correlation_id,
)
from snaketracker.infrastructure.observability.metrics import PlatformMetrics
from snaketracker.presentation.health import create_health_router


def create_application(*, readiness: ReadinessPort) -> FastAPI:
    """Compose the Phase 1 application without product routes."""
    app = FastAPI(title="SnakeTracker", version="0.1.0", docs_url=None, redoc_url=None)
    metrics = PlatformMetrics()
    app.include_router(create_health_router(readiness, metrics))

    @app.middleware("http")
    async def correlation_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = normalize_correlation_id(request.headers.get("X-Request-ID"))
        token = correlation_context.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_context.reset(token)
        response.headers["X-Request-ID"] = correlation_id
        return response

    return app
