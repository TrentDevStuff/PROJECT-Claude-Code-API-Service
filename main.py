"""
Claude Code API Service
A flexible, reusable API service that wraps Claude Code CLI for rapid prototyping.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from forgg_observability import init_telemetry, setup_logging
from forgg_observability.middleware.fastapi import ForggLoggingMiddleware

from src.api import initialize_services
from src.api import router as api_router
from src.audit_logger import AuditLogger
from src.auth import AuthManager, initialize_auth
from src.budget_manager import BudgetManager
from src.cache import RedisCache
from src.middleware import CCARequestIdSpanProcessor, RequestIDMiddleware
from src.permission_manager import PermissionManager
from src.settings import settings
from src.websocket import _streamer, initialize_websocket, websocket_endpoint
from src.circuit_breaker import CircuitBreaker
from src.direct_completion import DirectCompletionClient
from src.error_tracker import ErrorTracker
from src.worker_pool import WorkerPool

# Logger handle — actual logging configuration happens in lifespan() via
# forgg_observability.setup_logging so structlog/OTel context is present
# from the first request. Module-level imports above may emit a few stdlib
# log lines before that runs; those use Python's default handler.
logger = logging.getLogger(__name__)

SERVICE_NAME = "claude-code-api-service"

# Whitelist of CCA-emitted extra fields. Merged with forgg's
# DEFAULT_ALLOWED_LOG_FIELDS inside setup_logging(). Anything outside
# this list will trigger a structlog warning (governance signal).
ALLOWED_EXTRA_LOG_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "max_workers",
    "service",
    "detail",
    # Error observability
    "error_category",
    "upstream_status",
    "is_retryable",
    "circuit_state",
    "retry_count",
    "task_id",
    "model",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    # Prompt caching observability
    "cache_creation_tokens",
    "cache_read_tokens",
    "cache_hit_ratio",
    "cache_breakpoints",
    "has_tool_use",
    # Tool calling
    "tool_name",
    "tool_id",
    "overhead_ms",
)

# Global service instances
worker_pool: WorkerPool | None = None
budget_manager: BudgetManager | None = None
auth_manager: AuthManager | None = None
permission_manager: PermissionManager | None = None
audit_logger: AuditLogger | None = None
cache: RedisCache | None = None
sdk_client: DirectCompletionClient | None = None
sdk_circuit_breaker: CircuitBreaker | None = None
cli_circuit_breaker: CircuitBreaker | None = None
error_tracker_instance: ErrorTracker | None = None

# Lifecycle flags
_start_time: float | None = None
_shutting_down: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes and cleans up all services with graceful shutdown.
    """
    global worker_pool, budget_manager, auth_manager, permission_manager
    global audit_logger, cache, sdk_client, sdk_circuit_breaker, cli_circuit_breaker
    global error_tracker_instance, _start_time, _shutting_down

    _start_time = time.time()
    _shutting_down = False

    # Strip env vars that break Claude CLI subprocesses (e.g. when service
    # is started from inside a Claude Code session).
    for _var in ("CLAUDECODE", "CLAUDE_CODE_SESSION"):
        os.environ.pop(_var, None)

    # Initialize OTel tracing + structlog FIRST so every subsequent log line
    # carries service.name + trace_id and any startup span has a parent
    # context to attach to. Disable instrumentors for connectors CCA does
    # not use (no Postgres / no Mongo) to avoid harmless WARNING noise from
    # the v0.3.0 "missing instrumentor" banner.
    init_telemetry(
        service_name=SERVICE_NAME,
        service_version=app.version,
        environment=os.getenv("ENVIRONMENT", "development"),
        enable_asyncpg=False,
        enable_psycopg=False,
        enable_pymongo=False,
    )
    setup_logging(
        service_name=SERVICE_NAME,
        allowed_extra_fields=ALLOWED_EXTRA_LOG_FIELDS,
        log_level=settings.log_level.upper(),
        json_output=settings.log_json,
    )

    # Register the CCA request-id span processor so every span emitted
    # during a request carries `forgg.cca_request_id` for cross-service
    # correlation with ACA (per MSG-CCA-20260501-002-to-ACA).
    from opentelemetry import trace as _otel_trace
    _provider = _otel_trace.get_tracer_provider()
    if hasattr(_provider, "add_span_processor"):
        _provider.add_span_processor(CCARequestIdSpanProcessor())
    else:
        logger.warning(
            "OTel tracer provider missing add_span_processor; "
            "forgg.cca_request_id span attribute will not be emitted"
        )

    # Startup: Initialize services
    worker_pool = WorkerPool(max_workers=settings.max_workers, mcp_config=settings.mcp_config)
    worker_pool.start()

    budget_manager = BudgetManager(db_path=settings.db_path)
    auth_manager = AuthManager(db_path=settings.auth_db_path)
    permission_manager = PermissionManager(db_path=settings.db_path)
    audit_logger = AuditLogger(db_path=settings.db_path)

    # Initialize Redis cache (non-fatal if unavailable)
    cache = RedisCache()

    # Initialize direct SDK client (non-fatal if API key unavailable)
    try:
        sdk_client = DirectCompletionClient()
        logger.info("Direct SDK completion client ready")
    except Exception as e:
        logger.warning("SDK client unavailable (CLI path still works): %s", e)
        sdk_client = None

    # Initialize circuit breakers
    sdk_circuit_breaker = CircuitBreaker(
        failure_threshold=settings.circuit_breaker_threshold,
        recovery_timeout=settings.circuit_breaker_recovery_seconds,
        name="sdk",
    )
    cli_circuit_breaker = CircuitBreaker(
        failure_threshold=settings.circuit_breaker_threshold,
        recovery_timeout=settings.circuit_breaker_recovery_seconds,
        name="cli",
    )

    # Initialize error tracker
    error_tracker_instance = ErrorTracker(window_seconds=300.0)

    # Initialize API services
    initialize_services(
        worker_pool, budget_manager, permission_manager, sdk_client,
        sdk_cb=sdk_circuit_breaker, cli_cb=cli_circuit_breaker,
        tracker=error_tracker_instance,
    )
    initialize_auth(auth_manager)

    # Initialize WebSocket service
    initialize_websocket(worker_pool, budget_manager, permission_manager, audit_logger)

    logger.info("Worker pool started", extra={"max_workers": settings.max_workers})
    logger.info("Budget manager initialized")
    logger.info("Auth manager initialized")
    logger.info("Redis cache %s", "connected" if cache.is_connected() else "unavailable")
    logger.info("API services ready")
    logger.info("WebSocket streaming ready")

    yield

    # ------- Graceful shutdown -------
    _shutting_down = True
    logger.info("Shutdown initiated")

    # 1. Close WebSocket connections
    if _streamer and _streamer.active_connections:
        for _conn_id, ws in list(_streamer.active_connections.items()):
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass
        logger.info("WebSocket connections closed")

    # 2. Drain worker pool
    if worker_pool:
        completed, killed = worker_pool.drain(timeout=settings.shutdown_timeout)
        logger.info(
            "Worker pool drained",
            extra={
                "service": "worker_pool",
                "detail": f"completed={completed} killed={killed}",
            },
        )

    # 3. Close Redis
    if cache:
        cache.close()

    # 4. Close audit DB (aiosqlite connections are per-call, nothing to flush)

    logger.info("Shutdown complete")


app = FastAPI(
    title="Claude Code API Service",
    description="API wrapper around Claude Code CLI for rapid prototyping",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware order matters. ASGI applies middleware bottom-up at request
# time, so the LAST add_middleware call is the OUTERMOST wrapper. We want
# CORS outermost (sees every request, including preflight), then forgg
# logging (needs request_id from RequestIDMiddleware), then RequestID
# innermost (sets the request_id structlog binding).
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ForggLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


# ============================================================================
# Health & Readiness Models
# ============================================================================


class ServiceHealth(BaseModel):
    status: str
    detail: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float | None = None
    services: dict[str, ServiceHealth]


class ReadyResponse(BaseModel):
    ready: bool
    reason: str | None = None


# ============================================================================
# Health & Readiness Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Deep health check — reports real status of every subsystem.
    Returns 200 even when degraded so monitoring can parse the body.
    """
    svc: dict[str, ServiceHealth] = {}

    # Worker pool
    if worker_pool and worker_pool.running:
        pool_health = worker_pool.health_status()
        svc["worker_pool"] = ServiceHealth(
            status=pool_health["status"],
            detail=pool_health,
        )
    else:
        svc["worker_pool"] = ServiceHealth(status="unavailable")

    # Redis
    if cache and cache.is_connected():
        svc["redis"] = ServiceHealth(status="ok")
    else:
        svc["redis"] = ServiceHealth(status="unavailable")

    # Audit DB — lightweight probe
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("SELECT 1")
        svc["audit_db"] = ServiceHealth(status="ok")
    except Exception as exc:
        svc["audit_db"] = ServiceHealth(status="unavailable", detail={"error": str(exc)})

    # Budget / Auth managers
    svc["budget_manager"] = ServiceHealth(status="ok" if budget_manager else "unavailable")
    svc["auth_manager"] = ServiceHealth(status="ok" if auth_manager else "unavailable")

    # Error tracker
    if error_tracker_instance:
        total_errs = error_tracker_instance.total_errors()
        svc["error_rates"] = ServiceHealth(
            status="ok" if total_errs < 50 else "degraded",
            detail=error_tracker_instance.summary(),
        )

    # Circuit breakers
    if sdk_circuit_breaker:
        svc["sdk_circuit_breaker"] = ServiceHealth(
            status="ok" if sdk_circuit_breaker.state == "closed" else "degraded",
            detail=sdk_circuit_breaker.status(),
        )
    if cli_circuit_breaker:
        svc["cli_circuit_breaker"] = ServiceHealth(
            status="ok" if cli_circuit_breaker.state == "closed" else "degraded",
            detail=cli_circuit_breaker.status(),
        )

    overall = "ok" if all(s.status == "ok" for s in svc.values()) else "degraded"
    uptime = round(time.time() - _start_time, 1) if _start_time else None

    return HealthResponse(
        status=overall,
        version=app.version,
        uptime_seconds=uptime,
        services=svc,
    )


@app.get("/ready", response_model=ReadyResponse)
async def ready():
    """
    Readiness probe — returns 200 when the service can accept traffic,
    503 during startup or shutdown.
    """
    if _shutting_down:
        return ReadyResponse(ready=False, reason="shutting_down")

    if _start_time is None:
        return ReadyResponse(ready=False, reason="starting")

    # All critical services must be initialized
    if not worker_pool or not worker_pool.running:
        return ReadyResponse(ready=False, reason="worker_pool_not_ready")
    if not budget_manager:
        return ReadyResponse(ready=False, reason="budget_manager_not_ready")
    if not auth_manager:
        return ReadyResponse(ready=False, reason="auth_manager_not_ready")

    return ReadyResponse(ready=True)


@app.get("/")
def root():
    """Root endpoint with API info"""
    return {
        "name": "Claude Code API Service",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "endpoints": {
            "chat": "/v1/chat/completions",
            "batch": "/v1/batch",
            "usage": "/v1/usage",
            "route": "/v1/route",
            "stream": "ws://localhost:8006/v1/stream",
        },
    }


@app.websocket("/v1/stream")
async def stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming chat.

    Protocol:
    - Client sends: {"type": "chat", "model": "haiku", "messages": [...]}
    - Server streams: {"type": "token", "content": "..."}
    - Server finishes: {"type": "done", "usage": {...}, "cost": 0.001}
    """
    await websocket_endpoint(websocket)


if __name__ == "__main__":
    # Force asyncio event loop — uvloop's idle callback deadlocks when the
    # WorkerPool monitor thread contends for the GIL via threading.Lock.
    # See process sample: main thread stuck in lock_PyThread_acquire_lock
    # inside uv__run_idle → _on_idle → task_step → PyObject_GetAttr.
    uvicorn.run(app, host="0.0.0.0", port=settings.port, loop="asyncio")
