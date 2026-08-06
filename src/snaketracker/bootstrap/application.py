"""FastAPI composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from snaketracker.application.household_bootstrap import HouseholdBootstrapService
from snaketracker.application.identity import IdentityService
from snaketracker.application.ports.readiness import ReadinessPort
from snaketracker.application.readiness import PlatformReadiness
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.observability.correlation import (
    correlation_context,
    normalize_correlation_id,
)
from snaketracker.infrastructure.observability.logging import configure_logging
from snaketracker.infrastructure.observability.metrics import PlatformMetrics
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.presentation.health import create_health_router
from snaketracker.presentation.web import create_web_router


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
    static_directory = Path(__file__).parents[1] / "presentation" / "static"
    app.mount("/static", StaticFiles(directory=static_directory), name="static")

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

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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
    if settings.runtime_secret is not None and compatibility.normal_readiness:
        secret = settings.runtime_secret.get_secret_value().encode()
        password_hasher = Argon2PasswordHasher()
        bootstrap_repository = SQLAlchemyHouseholdBootstrapRepository(engine)
        identity_repository = SQLAlchemyIdentityRepository(engine)
        app.include_router(
            create_web_router(
                bootstrap_service=HouseholdBootstrapService(
                    bootstrap_repository,
                    password_hasher,
                    command_hash_secret=secret,
                ),
                identity_service=IdentityService(
                    identity_repository,
                    password_hasher,
                    secret=secret,
                    idle_timeout=timedelta(minutes=30),
                    absolute_timeout=timedelta(hours=12),
                    rate_limit=5,
                    rate_window=timedelta(minutes=15),
                    block_duration=timedelta(minutes=15),
                ),
                is_bootstrapped=identity_repository.has_users,
                secure_cookie=settings.session_cookie_secure,
                expected_origin=(
                    str(settings.external_origin).rstrip("/")
                    if settings.external_origin is not None
                    else None
                ),
            )
        )
    app.state.database_engine = engine
    app.state.compatibility = compatibility
    return app


def application_factory() -> FastAPI:
    """Uvicorn factory that validates environment configuration at startup."""
    return build_application(load_settings())
