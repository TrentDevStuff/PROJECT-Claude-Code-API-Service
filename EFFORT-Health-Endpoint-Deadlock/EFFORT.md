---
type: effort
effort_id: EFFORT-Health-Endpoint-Deadlock
project: PROJECT-Claude-Code-API-Service
status: planning
priority: medium
progress: 0%
created: 2026-04-01T00:00:00Z
last_updated: 2026-04-01T00:00:00Z
linked_goal: null
---

# EFFORT: Fix /health Endpoint Event Loop Deadlock

## Overview

The `/health` endpoint in `main.py` calls `async with aiosqlite.connect(settings.db_path)` to probe the audit database. This call creates a background thread with a threading.Lock that can deadlock the asyncio event loop under certain conditions — specifically when called during early startup or under memory pressure.

This was discovered during investigation of a complete service hang (commit `3e00942`). The immediate fix was switching the service orchestrator's health probe from `/health` to `/ready`, but the `/health` endpoint itself remains broken for direct callers (monitoring, curl, browser).

## Root Cause Analysis

Process sampling (`sample <pid>`) showed the main thread stuck in:

```
task_step_impl → gen_send_ex2 → _PyEval_EvalFrameDefault →
PyObject_GetAttr → _PyObject_GenericGetAttrWithDict →
PyObject_CallOneArg → lock_PyThread_acquire_lock →
_pthread_cond_wait
```

The `aiosqlite.connect()` call:
1. Spawns a background thread to run synchronous sqlite3
2. Uses `threading.Lock` for coordination between the event loop and the sqlite thread
3. Under GIL contention (from WorkerPool monitor thread or memory pressure), the lock acquisition in the asyncio task can deadlock

The `/ready` endpoint works fine because it only checks `if worker_pool and worker_pool.running` — no threading, no locks.

## Investigation Scope

Before implementing a fix, explore and understand:

1. **Is aiosqlite the right tool here?** The health check only needs `SELECT 1` — a synchronous `sqlite3.connect()` in a `run_in_executor()` might be simpler and avoid the aiosqlite thread machinery entirely.

2. **Does aiosqlite have known deadlock issues?** Check GitHub issues, especially with Python 3.12 and the free-threaded GIL changes.

3. **What does the /health endpoint actually need?** Currently it probes: worker_pool, redis, audit_db, budget_manager, auth_manager, error_tracker, circuit_breakers. The audit_db probe is the only one that blocks. Could it be removed or made best-effort with a timeout?

4. **Could `asyncio.wait_for()` with a timeout wrapper prevent the deadlock?** Wrap the aiosqlite call in a 2-second timeout so even if it hangs, it doesn't poison the event loop.

5. **Are there other aiosqlite calls in request paths that could deadlock?** Check `src/budget_manager.py` — every budget check does `async with aiosqlite.connect(...)`.

## Proposed Approaches

### Option A: Replace aiosqlite probe with run_in_executor
```python
import sqlite3
from asyncio import get_event_loop

async def _probe_db():
    loop = get_event_loop()
    def _check():
        conn = sqlite3.connect(settings.db_path, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
    await loop.run_in_executor(None, _check)
```

### Option B: Timeout wrapper around aiosqlite
```python
try:
    async with asyncio.timeout(2):
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("SELECT 1")
    svc["audit_db"] = ServiceHealth(status="ok")
except asyncio.TimeoutError:
    svc["audit_db"] = ServiceHealth(status="timeout")
```

### Option C: Remove DB probe from /health entirely
The audit DB is non-critical — if it's down, the service still works (just no audit logging). Make `/health` only check critical subsystems.

### Option D: Replace aiosqlite entirely
If aiosqlite's threading model is fundamentally incompatible with this service's thread profile (WorkerPool monitor thread, circuit breaker timers), replace it with synchronous sqlite3 in `run_in_executor()` throughout `budget_manager.py`.

## Success Criteria

- [ ] `/health` endpoint responds within 2 seconds under all conditions
- [ ] Service orchestrator can use `/health` (not just `/ready`) without deadlocking
- [ ] No regression in existing tests
- [ ] Budget manager operations don't deadlock under load

## Files to Investigate

- `main.py` — `/health` endpoint (lines 213-277)
- `src/budget_manager.py` — all aiosqlite usage
- `src/worker_pool.py` — monitor thread interaction
- `requirements.txt` — aiosqlite version vs installed version

## Related

- Commit `3e00942` — event loop deadlock fix (BaseHTTPMiddleware + WorkerPool + services.yaml)
- `services.yaml` — currently uses `/ready` as workaround
