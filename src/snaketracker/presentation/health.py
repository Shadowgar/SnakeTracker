"""Platform health and internal metrics routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from snaketracker.application.ports.readiness import HealthMetricsPort, ReadinessPort


def create_health_router(readiness: ReadinessPort, metrics: HealthMetricsPort) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/health/ready")
    def readiness_check() -> Response:
        result = readiness.check()
        metrics.set_readiness(ready=result.is_ready)
        if not result.is_ready:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "reason": result.reason_code},
            )
        return JSONResponse(content={"status": "ready"})

    @router.get("/internal/metrics", include_in_schema=False)
    def internal_metrics() -> Response:
        return Response(content=metrics.render(), media_type=CONTENT_TYPE_LATEST)

    return router
