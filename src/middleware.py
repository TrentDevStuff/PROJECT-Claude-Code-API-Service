"""
Request middleware for correlation and observability.

Adds a unique request ID to every HTTP request for log correlation.

Uses a pure ASGI middleware implementation instead of Starlette's
BaseHTTPMiddleware to avoid the anyio task-group deadlock that occurs
in Starlette >= 0.38 under GIL contention from background threads.

Also exports a contextvar (`cca_request_id_ctx`) and a custom OTel
SpanProcessor (`CCARequestIdSpanProcessor`) that broadcasts the per-request
UUID onto every span emitted during the request as `forgg.cca_request_id`.
This is the CCA-side of the ACA↔CCA attribute-correlation contract
(MSG-ACA-20260430-001 / MSG-CCA-20260501-002): ACA's `agent.execute` parent
span and CCA's spans share the attribute, enabling cross-service joins in
SigNoz without traceparent waterfall propagation (which the Bun-binary SDK
subprocess does not support).
"""

import contextvars
import logging
import time
import uuid

from opentelemetry.sdk.trace import SpanProcessor
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Per-request UUID, populated by RequestIDMiddleware. Read by
# CCARequestIdSpanProcessor at span-start time so every span in the trace
# carries `forgg.cca_request_id`.
cca_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "forgg_cca_request_id", default=None
)


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

        # Populate contextvar so CCARequestIdSpanProcessor can copy it onto
        # every OTel span emitted during this request as `forgg.cca_request_id`.
        cca_request_id_ctx.set(request_id)

        start = time.perf_counter()
        status_code = 0

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject X-Request-ID into response headers, plus the
                # X-Forgg-CCA-Request-Id alias used by the ACA↔CCA cross-service
                # correlation contract (same value, namespaced header).
                raw_headers = list(message.get("headers", []))
                encoded_id = request_id.encode("latin-1")
                raw_headers.append((b"x-request-id", encoded_id))
                raw_headers.append((b"x-forgg-cca-request-id", encoded_id))
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


class CCARequestIdSpanProcessor(SpanProcessor):
    """OTel SpanProcessor that copies the per-request UUID from
    ``cca_request_id_ctx`` onto every span as ``forgg.cca_request_id``.

    Registered with the global tracer provider in ``main.py`` after
    ``init_telemetry()``. Runs at span-start so the attribute is recorded
    on the span before it is exported, regardless of which middleware layer
    or instrumentor created the span.
    """

    def on_start(self, span, parent_context=None):  # type: ignore[override]
        request_id = cca_request_id_ctx.get()
        if request_id and span.is_recording():
            span.set_attribute("forgg.cca_request_id", request_id)

    def on_end(self, span):  # type: ignore[override]
        pass

    def shutdown(self):  # type: ignore[override]
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # type: ignore[override]
        return True
