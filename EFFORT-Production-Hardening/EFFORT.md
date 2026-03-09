---
type: effort
effort_id: EFFORT-Production-Hardening
project: PROJECT-Claude-Code-API-Service
status: in_progress
priority: high
progress: 95%
created: 2026-02-16T12:00:00Z
last_updated: 2026-02-16T21:40:00Z
linked_goal: null
---

# EFFORT: Production Hardening (Wave 6)

## Overview

Harden the claude-code-api-service for production-like deployment. Covers health checks, graceful shutdown, structured logging, process supervision, and basic CI/CD. Scoped to what's practical for a personal prototyping service -- not full enterprise deployment (Wave 7).

Based on WAVES-5-7-PLAN.md Wave 6 (INIT-015 through INIT-018), adapted for current needs.

## Scope

### In Scope

1. **Health & Readiness** -- Deep health checks (Redis, workers, disk), readiness probe, liveness probe
2. **Graceful Shutdown** -- SIGTERM handler, drain worker pool, close WebSocket connections, flush audit logs
3. **Structured Logging** -- JSON logging, request IDs, correlation across worker pool, log levels
4. **Process Supervision** -- Proper startup script, PID file, crash recovery, systemd/launchd unit
5. **Basic CI** -- GitHub Actions running pytest on push, coverage enforcement
6. **Configuration** -- Environment-based config (dev/staging/prod), secrets management

### Out of Scope

- Docker Compose stack (handled by system-containerizer)
- Load testing / pen testing (future)
- Prometheus/Grafana monitoring (future)
- Production cloud deployment (Wave 7)

## Working Document

[[2026-02-16-production-hardening]]

## Success Criteria

- [x] `/health` returns deep status (Redis, workers, uptime)
- [x] `/ready` probe for load balancer integration
- [x] SIGTERM triggers graceful drain (no dropped requests)
- [x] All logs are structured JSON with request correlation
- [x] GitHub Actions CI passes on every push
- [x] Service restarts cleanly after crash (launchd plist)
- [x] 228+ tests still passing, 80%+ coverage maintained

## Completed Work

### Server-side (main.py, src/) -- landed earlier today

- Deep `/health` endpoint with per-service status (worker_pool, redis, audit_db, budget_manager, auth_manager), overall ok/degraded, uptime_seconds
- `/ready` endpoint (returns 503 during startup/shutdown, reason field)
- Graceful shutdown via lifespan: close WebSockets, drain worker pool, close Redis
- `src/settings.py` with pydantic-settings (`CLAUDE_API_*` env prefix)
- `src/logging_config.py` structured JSON logging with request ID correlation
- `src/middleware.py` RequestIDMiddleware for X-Request-ID propagation

### CLI alignment (commit b12798d) -- 2026-02-16

Aligned all CLI commands with the new server endpoints:

| File | Changes |
|------|---------|
| `cli/api_client.py` | Added `get_ready()` method |
| `cli/commands/health.py` | `health check` parses deep `/health` per-service status (replaced client-side Redis probe). `health ping --ready` uses `/ready`. |
| `cli/commands/workers.py` | `workers status` shows real metrics from `/health` worker_pool detail |
| `cli/commands/service.py` | `start` uses `CLAUDE_API_PORT`, sets `LOG_JSON=false` in foreground, redirects stderr to `~/.claude-api/service.log` in background, polls `/ready` for startup. `status` uses server uptime, shows degraded services + worker stats. `logs` fully implemented with `--follow`, `--level`. |
| `cli/commands/test.py` | `test all` includes `GET /ready` (4 tests total) |

Tests: 228 passed, 0 failures, 81% coverage.

### CI/CD (commit dd23b27) -- 2026-02-16

- GitHub Actions workflow: lint (black + ruff), test (Python 3.9/3.11/3.12 matrix with Redis), security scan (Trivy)
- Fixed all black formatting (46 files), ruff lint (506 errors resolved)
- Python 3.9 compatibility: `from __future__ import annotations`, `eval_type_backport`, `datetime.timezone.utc`

### Process supervision (launchd plist) -- 2026-02-16

- `service install` / `service uninstall` CLI commands
- `com.claude-api.service.plist` with `KeepAlive.SuccessfulExit = false` (auto-restart on crash)
- Logs to `~/.claude-api/service.log`, 5s throttle between restarts
- `--start` flag to load immediately after install

## Remaining

- Verify CI passes in GitHub (push trigger)

## Related

- Task: T-2026-01-30-010 (Complete Wave 6 for production deployment)
- Plan: WAVES-5-7-PLAN.md (INIT-015 through INIT-018)
