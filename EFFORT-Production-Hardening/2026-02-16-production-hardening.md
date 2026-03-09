---
created: 2026-02-16T12:00:00Z
updated: 2026-02-16T12:00:00Z
type: working-document
effort: EFFORT-Production-Hardening
---

# Production Hardening -- Working Document

## Current State Assessment

The service runs and passes all tests, but lacks production affordances:

| Area | Current | Target |
|------|---------|--------|
| Health check | `/health` returns `{"status": "ok"}` (shallow) | Deep check: Redis, workers, uptime, version |
| Shutdown | Process kill, no drain | SIGTERM -> drain workers -> close WS -> flush logs -> exit |
| Logging | Print statements, no structure | JSON logs, request IDs, correlation |
| Process mgmt | Manual `uvicorn` start | Startup script with PID, crash restart |
| CI | None | GitHub Actions: lint + pytest on push |
| Config | Hardcoded defaults | Env-based config class (dev/staging/prod) |

## Implementation Plan

### Phase 1: Deep Health & Readiness (src/api.py)

- Enhance `/health` to check Redis connectivity, worker pool status, uptime
- Add `/ready` endpoint (returns 503 during startup/shutdown)
- Add `/version` or include version in health response

### Phase 2: Graceful Shutdown (main.py, src/worker_pool.py)

- Register SIGTERM/SIGINT handlers
- Set shutdown flag -> reject new requests (503)
- Drain active workers (wait up to 30s)
- Close WebSocket connections with 1001 Going Away
- Flush audit logger
- Exit cleanly

### Phase 3: Structured Logging

- Add `structlog` or `python-json-logger` dependency
- Create logging config with JSON formatter
- Add request ID middleware (X-Request-ID header)
- Propagate request ID to worker pool and audit logger
- Replace print() calls with structured log calls

### Phase 4: Process Supervision

- Create `scripts/start.sh` with PID tracking
- Create launchd plist for macOS auto-restart
- Add `scripts/stop.sh` for graceful shutdown

### Phase 5: GitHub Actions CI

- `.github/workflows/test.yml`: checkout, install deps, pytest
- Coverage enforcement (80% minimum)
- Run on push to main and PRs

### Phase 6: Environment Config

- Create `src/settings.py` with pydantic-settings BaseSettings
- Support `.env` file and environment variables
- Profiles: dev (verbose logging, auto-reload), prod (JSON logs, no debug)

---

## Notes & Decisions

_(Working area -- add notes as we implement)_
