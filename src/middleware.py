"""
Request middleware for correlation and observability.

Adds a unique request ID to every HTTP request for log correlation.

Uses a pure ASGI middleware implementation instead of Starlette's
BaseHTTPMiddleware to avoid the anyio task-group deadlock that occurs
in Starlette >= 0.38 under GIL contention from background threads.
"""

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Injects X-Request-ID into every request/response and logs request lifecycle.

    Pure ASGI implementation — no BaseHTTPMiddleware, no anyio task groups,
    no memory-object streams. Immune to GIL contention from daemon threads.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate request ID
        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode("latin-1")
            or str(uuid.uuid4())
        )

        # Stash in scope for downstream access (e.g. request.state.request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        start = time.perf_counter()
        status_code = 0

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject X-Request-ID into response headers
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            method = scope.get("method", "?")
            path = scope.get("path", "?")
            logger.info(
                "%s %s %s %.1fms",
                method,
                path,
                status_code,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
