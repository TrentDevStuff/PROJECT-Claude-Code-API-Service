"""
Claude Code API Service
A flexible, reusable API service that wraps Claude Code CLI for rapid prototyping.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api import initialize_services
from src.api import router as api_router
from src.audit_logger import AuditLogger
from src.auth import AuthManager, initialize_auth
from src.budget_manager import BudgetManager
from src.cache import RedisCache
from src.logging_config import setup_logging
from src.middleware import RequestIDMiddleware
from src.permission_manager import PermissionManager
from src.settings import settings
from src.websocket import _streamer, initialize_websocket, websocket_endpoint
from src.direct_completion import DirectCompletionClient
from src.worker_pool import WorkerPool

# Configure logging early (before anything else logs)
setup_logging(level=settings.log_level, json_format=settings.log_json)
logger = logging.getLogger(__name__)

# Global service instances
worker_pool: WorkerPool | None = None
budget_manager: BudgetManager | None = None
auth_manager: AuthManager | None = None
permission_manager: PermissionManager | None = None
audit_logger: AuditLogger | None = None
cache: RedisCache | None = None
sdk_client: DirectCompletionClient | None = None

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
    global audit_logger, cache, sdk_client, _start_time, _shutting_down

    _start_time = time.time()
    _shutting_down = False

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

    # Initialize API services
    initialize_services(worker_pool, budget_manager, permission_manager, sdk_client)
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

# Request ID middleware (must be added before CORS so it wraps all requests)
app.add_middleware(RequestIDMiddleware)

# Enable CORS for web clients
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
        svc["worker_pool"] = ServiceHealth(
            status="ok",
            detail={
                "running": worker_pool.running,
                "active_workers": worker_pool.active_workers,
                "max_workers": worker_pool.max_workers,
                "queued_tasks": worker_pool.task_queue.qsize(),
            },
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
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
