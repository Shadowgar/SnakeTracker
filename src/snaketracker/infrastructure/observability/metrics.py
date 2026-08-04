"""Low-cardinality platform metrics."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Gauge, generate_latest


class PlatformMetrics:
    """Own an isolated registry for one application instance."""

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._readiness = Gauge(
            "snaketracker_readiness",
            "Whether normal application traffic may be accepted.",
            registry=self._registry,
        )

    def set_readiness(self, *, ready: bool) -> None:
        self._readiness.set(1 if ready else 0)

    def render(self) -> bytes:
        return generate_latest(self._registry)
