"""Fail-closed public delivery and bounded single-process request accounting."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from starlette.datastructures import MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_PREFIXES = ("/p/", "/c/", "/m/")
logger = logging.getLogger(__name__)
NO_STORE = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
}


class PublicRequestBudget:
    """Fixed-size, rolling-minute budgets; new clients cannot evict active limits."""

    def __init__(self, *, per_client: int, total: int, max_clients: int = 1024) -> None:
        self._per_client = per_client
        self._total = total
        self._max_clients = max_clients
        self._clients: dict[str, deque[float]] = {}
        self._requests: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, client: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - 60
        with self._lock:
            while self._requests and self._requests[0] <= cutoff:
                self._requests.popleft()
            expired = []
            for key, timestamps in self._clients.items():
                while timestamps and timestamps[0] <= cutoff:
                    timestamps.popleft()
                if not timestamps:
                    expired.append(key)
            for key in expired:
                del self._clients[key]
            if len(self._requests) >= self._total:
                return False
            if client not in self._clients:
                if len(self._clients) >= self._max_clients:
                    return False
                self._clients[client] = deque()
            timestamps = self._clients[client]
            if len(timestamps) >= self._per_client:
                return False
            timestamps.append(current)
            self._requests.append(current)
            return True


class PublicSharingGuard:
    """Run before route lookup, including missing paths, HEAD and denied requests.

    The application trusts only the ASGI client address. Proxy trust and aggregate
    multi-process limits remain a production-release qualification requirement.
    """

    def __init__(
        self, app: ASGIApp, *, enabled: bool, per_client: int = 240, total: int = 1200
    ) -> None:
        self._app = app
        self._enabled = enabled
        self._budget = PublicRequestBudget(per_client=per_client, total=total)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(PUBLIC_PREFIXES):
            await self._app(scope, receive, send)
            return

        response_started = False

        async def private_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                for key, value in NO_STORE.items():
                    headers[key] = value
            await send(message)

        if not self._enabled:
            await PlainTextResponse("Not found", status_code=404)(scope, receive, private_send)
            return
        client = scope.get("client")
        address = str(client[0]) if client else "unknown"
        if not self._budget.allow(address):
            await PlainTextResponse(
                "Please try again shortly", status_code=429, headers={"Retry-After": "60"}
            )(scope, receive, private_send)
            return
        try:
            await self._app(scope, receive, private_send)
        except Exception:
            if response_started:
                raise
            logger.exception("Public sharing request failed")
            await PlainTextResponse("Service unavailable", status_code=500)(
                scope, receive, private_send
            )
