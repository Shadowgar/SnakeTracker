"""FastAPI composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from starlette.types import Lifespan

from snaketracker.application.ports.readiness import ReadinessPort
from snaketracker.application.readiness import PlatformReadiness
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth
from snaketracker.infrastructure.observability.correlation import (
    correlation_context,
    normalize_correlation_id,
)
from snaketracker.infrastructure.observability.logging import configure_logging
from snaketracker.infrastructure.observability.metrics import PlatformMetrics
from snaketracker.presentation.health import create_health_router


def create_application(
    *, readiness: ReadinessPort, lifespan: Lifespan[FastAPI] | None = None
) -> FastAPI:
    """Compose the Phase 1 application without product routes."""
    app = FastAPI(
        title="SnakeTracker",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
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


def build_application(settings: Settings) -> FastAPI:
    """Build the production composition from validated settings."""
    configure_logging(settings.log_level)
    engine = create_sqlite_engine(
        settings.database_path,
        require_local_storage=settings.environment is Environment.PRODUCTION,
    )
    compatibility = inspect_startup_compatibility(engine)
    readiness = PlatformReadiness(
        database=SQLAlchemyDatabaseHealth(engine),
        compatibility=compatibility,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app = create_application(readiness=readiness, lifespan=lifespan)
    app.state.database_engine = engine
    app.state.compatibility = compatibility
    return app


def application_factory() -> FastAPI:
    """Uvicorn factory that validates environment configuration at startup."""
    return build_application(load_settings())
