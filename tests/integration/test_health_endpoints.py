from __future__ import annotations

import httpx
import pytest

from snaketracker.application.ports.readiness import ReadinessResult
from snaketracker.bootstrap.application import create_application


class StubReadiness:
    def __init__(self, result: ReadinessResult) -> None:
        self.result = result

    def check(self) -> ReadinessResult:
        return self.result


@pytest.mark.anyio
async def test_liveness_and_ready_health_contracts() -> None:
    app = create_application(readiness=StubReadiness(ReadinessResult.ready()))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live", headers={"X-Request-ID": "request-123"})
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert live.headers["X-Request-ID"] == "request-123"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


@pytest.mark.anyio
async def test_readiness_failure_is_safe_and_metrics_have_bounded_labels() -> None:
    app = create_application(
        readiness=StubReadiness(ReadinessResult.unavailable("relational_schema_too_new"))
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready", headers={"X-Request-ID": "unsafe value"})
        metrics = await client.get("/internal/metrics")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason": "relational_schema_too_new",
    }
    assert response.headers["X-Request-ID"] != "unsafe value"
    assert b"snaketracker_readiness" in metrics.content
    assert b"household" not in metrics.content
    assert b"user" not in metrics.content
