"""FastAPI composition root."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from snaketracker.application.analytics import AnimalAnalyticsService
from snaketracker.application.animals import AnimalService
from snaketracker.application.attachments import AttachmentService
from snaketracker.application.backups import BackupService
from snaketracker.application.dashboard import DashboardStatisticsService
from snaketracker.application.enclosures import EnclosureService
from snaketracker.application.expenses import ExpenseService
from snaketracker.application.household_bootstrap import HouseholdBootstrapService
from snaketracker.application.identity import IdentityService
from snaketracker.application.inventory import InventoryService
from snaketracker.application.ports.readiness import ReadinessPort
from snaketracker.application.readiness import PlatformReadiness
from snaketracker.application.reminders import ReminderFactService, ReminderRuleService
from snaketracker.application.reports import ReportService
from snaketracker.application.search import SearchService
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.expenses.projections import SQLAlchemyExpenseCurrentProjection
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.inventory.projections import SQLAlchemyInventoryBalanceProjection
from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.repository import (
    SQLAlchemyNotificationIntentRepository,
)
from snaketracker.infrastructure.observability.correlation import (
    correlation_context,
    normalize_correlation_id,
)
from snaketracker.infrastructure.observability.logging import configure_logging
from snaketracker.infrastructure.observability.metrics import PlatformMetrics
from snaketracker.infrastructure.product_experience.projections import (
    ensure_product_projection_generations,
    product_projection_registry,
)
from snaketracker.infrastructure.product_experience.read_models import (
    SQLAlchemyProjectedEventReader,
)
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.search.fts import SQLAlchemyFTSSearchRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.notifications.service import NotificationIntentService
from snaketracker.presentation.health import create_health_router
from snaketracker.presentation.web import create_web_router
from snaketracker.worker.projections import ProjectionWorker

logger = logging.getLogger(__name__)


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

    @app.get("/service-worker.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(
            static_directory / "service-worker.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

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
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
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
    compatibility = inspect_startup_compatibility(engine, product_projection_registry)
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
        event_store = SQLAlchemyEventStore(engine)
        inventory_projection = SQLAlchemyInventoryBalanceProjection(engine)
        inventory_service = InventoryService(event_store, inventory_projection)
        animal_service = AnimalService(
            event_store,
            SQLAlchemyAnimalCurrentProjection(engine),
            inventory_projection=inventory_projection,
        )
        attachment_service = AttachmentService(
            animals=animal_service,
            repository=SQLAlchemyAttachmentRepository(engine),
            storage=LocalAttachmentStorage(
                settings.attachment_storage_path or settings.database_path.parent / "attachments"
            ),
        )
        enclosure_service = EnclosureService(
            event_store, SQLAlchemyEnclosureCurrentProjection(engine)
        )
        reminder_projection = SQLAlchemyReminderProjection(engine)
        expense_service = ExpenseService(event_store, SQLAlchemyExpenseCurrentProjection(engine))
        projection_manager = SQLiteProjectionGenerationManager(engine, product_projection_registry)
        projection_catch_up: Callable[[], object] | None = None
        if settings.environment is Environment.TEST:

            def catch_up_test_projections() -> object:
                test_manager = ensure_product_projection_generations(engine)
                return ProjectionWorker(
                    engine, test_manager, product_projection_registry
                ).run_once()

            projection_catch_up = catch_up_test_projections
        analytics_events = SQLAlchemyProjectedEventReader(
            engine,
            projection_manager,
            product_projection_registry,
            "measurement_analytics",
        )
        report_events = SQLAlchemyProjectedEventReader(
            engine, projection_manager, product_projection_registry, "report_facts"
        )
        dashboard_events = SQLAlchemyProjectedEventReader(
            engine,
            projection_manager,
            product_projection_registry,
            "dashboard_statistics",
        )
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
                animal_service=animal_service,
                attachment_service=attachment_service,
                backup_service=BackupService(SQLAlchemyBackupRepository(engine)),
                enclosure_service=enclosure_service,
                inventory_service=inventory_service,
                expense_service=expense_service,
                analytics_service=AnimalAnalyticsService(
                    animal_service, projected_events=analytics_events
                ),
                report_service=ReportService(
                    animal_service, expense_service, projected_events=report_events
                ),
                dashboard_statistics_service=DashboardStatisticsService(dashboard_events),
                reminder_rule_service=ReminderRuleService(event_store, reminder_projection),
                reminder_fact_service=ReminderFactService(event_store, reminder_projection),
                reminder_projection=reminder_projection,
                notification_intent_service=NotificationIntentService(
                    SQLAlchemyNotificationIntentRepository(engine)
                ),
                job_repository=SQLAlchemyJobRepository(engine),
                search_service=SearchService(
                    SQLAlchemyFTSSearchRepository(engine, projection_manager)
                ),
                projection_catch_up=projection_catch_up,
                is_bootstrapped=identity_repository.has_users,
                secure_cookie=settings.session_cookie_secure,
                expected_origin=(
                    str(settings.external_origin).rstrip("/")
                    if settings.external_origin is not None
                    else None
                ),
            )
        )
    elif settings.runtime_secret is None:
        logger.warning("Browser routes disabled because the runtime secret is not configured.")
    else:
        logger.warning(
            "Browser routes disabled because startup compatibility is not normal.",
            extra={"context": {"compatibility_reason": compatibility.reason_code}},
        )
    app.state.database_engine = engine
    app.state.compatibility = compatibility
    return app


def application_factory() -> FastAPI:
    """Uvicorn factory that validates environment configuration at startup."""
    return build_application(load_settings())
