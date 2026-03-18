---
created: 2026-03-18T10:00:00Z
updated: 2026-03-18T10:00:00Z
type: plan
backlinks: []
---

# PLAN: Phase 2 — Retry and Resilience

## Overview

Add intelligent retry logic and circuit breaking to prevent transient upstream failures from reaching callers. Phase 1 classifies errors correctly; Phase 2 automatically recovers from them when possible.

## Scope

Three components:
1. **SDK client hardening** — increase `max_retries`, configure timeouts
2. **Application-level retry** — retry around the `complete()` call for specific categories
3. **Circuit breaker** — trip after consecutive failures, half-open to probe recovery

## Files Changed

### 1. `src/direct_completion.py` — SDK client configuration

**What changes:**
- Configure `anthropic.Anthropic()` with `max_retries=4` (up from default 2)
- Add explicit `timeout=httpx.Timeout(60.0, connect=10.0)` to prevent indefinite hangs
- The SDK's built-in retry handles 429, 500, and connection errors with exponential backoff automatically

**Specific change in `__init__`:**
```python
import httpx

self.client = anthropic.Anthropic(
    max_retries=4,
    timeout=httpx.Timeout(60.0, connect=10.0),
)
```

**Why 4 retries:** The Anthropic SDK uses exponential backoff (0.5s, 1s, 2s, 4s). Total wait before giving up: ~7.5s. This covers typical Anthropic rate limit windows (usually resolve within 5-10s for per-minute limits).

### 2. New file: `src/circuit_breaker.py`

**Design:**
```
States:
  CLOSED (normal) --> OPEN (tripped) --> HALF_OPEN (probing)

Transitions:
  CLOSED --> OPEN: after `failure_threshold` consecutive failures
  OPEN --> HALF_OPEN: after `recovery_timeout` seconds
  HALF_OPEN --> CLOSED: on success
  HALF_OPEN --> OPEN: on failure
```

**Interface:**
```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "default",
    ):
        ...

    def allow_request(self) -> bool:
        """Returns True if the circuit allows a request through."""

    def record_success(self) -> None:
        """Record a successful call."""

    def record_failure(self, error_category: str | None = None) -> None:
        """Record a failed call. Only retryable categories count toward tripping."""

    @property
    def state(self) -> str:
        """Current state: 'closed', 'open', 'half_open'."""

    def status(self) -> dict:
        """Health check data for /health endpoint."""
```

**Key design decisions:**
- **Thread-safe** via `threading.Lock` (worker pool is thread-based)
- **Only retryable errors trip** — auth_error and bad_request do not count
- **Configurable via settings** — add to `src/settings.py`
- **Named instances** — one for SDK path, one for CLI path (they can fail independently)

**Retryable categories (from Phase 1):**
```python
RETRYABLE_CATEGORIES = {"rate_limited", "overloaded", "upstream_error", "timeout", "connection_error"}
```

### 3. `src/settings.py` — New configuration fields

**Additions:**
```python
sdk_max_retries: int = 4
sdk_timeout_seconds: float = 60.0
circuit_breaker_threshold: int = 5
circuit_breaker_recovery_seconds: float = 30.0
```

### 4. `src/api.py` — Integrate circuit breaker

**What changes:**
- Import and initialize circuit breaker instances during `initialize_services()`
- Before SDK `complete()` call: check `circuit_breaker.allow_request()`
- After result: call `record_success()` or `record_failure()`
- When circuit is open: return HTTP 503 with `Retry-After` header immediately (fast-fail)

**SDK path integration (around line 564-578):**
```python
if not sdk_circuit.allow_request():
    raise HTTPException(
        status_code=503,
        detail="Upstream API circuit breaker open -- too many recent failures",
        headers={"Retry-After": str(int(sdk_circuit.recovery_timeout))},
    )

result = await loop.run_in_executor(None, sdk_client.complete, ...)

if result.status == TaskStatus.COMPLETED:
    sdk_circuit.record_success()
else:
    sdk_circuit.record_failure(result.error_category)
```

CLI path: similar pattern with `cli_circuit`.

### 5. `main.py` — Circuit breaker lifecycle

**What changes:**
- Create circuit breaker instances in lifespan startup
- Pass them to `initialize_services()`
- Include circuit breaker status in `/health` endpoint

## Implementation Steps

1. Create `src/circuit_breaker.py` -- standalone module, no dependencies
2. Write `tests/test_circuit_breaker.py` -- state transitions, thread safety, retryable filtering
3. Update `src/settings.py` -- add 4 new config fields
4. Update `src/direct_completion.py` -- configure SDK client with settings
5. Update `src/api.py` -- integrate circuit breaker at SDK and CLI paths
6. Update `main.py` -- lifecycle management, health endpoint integration
7. Write integration tests -- circuit breaker tripping during repeated failures
8. Run full test suite

## Test Strategy

### New tests: `tests/test_circuit_breaker.py` (~12 tests)

- `test_initial_state_closed` -- starts closed
- `test_success_keeps_closed` -- successes don't change state
- `test_failures_trip_circuit` -- N consecutive failures --> open
- `test_open_rejects_requests` -- `allow_request()` returns False when open
- `test_recovery_timeout_half_opens` -- after timeout, state becomes half_open
- `test_half_open_success_closes` -- success in half_open --> closed
- `test_half_open_failure_reopens` -- failure in half_open --> open
- `test_non_retryable_errors_dont_trip` -- auth_error, bad_request don't count
- `test_success_resets_failure_count` -- success resets consecutive failures
- `test_thread_safety` -- concurrent record_failure from multiple threads
- `test_status_output` -- verify status() dict structure
- `test_configurable_thresholds` -- custom threshold and recovery values

### Updated tests in `tests/test_api.py` (~4 tests)

- `test_circuit_open_returns_503` -- verify fast-fail behavior
- `test_circuit_closes_after_success` -- verify recovery
- `test_circuit_breaker_in_health` -- verify appears in /health response
- `test_circuit_breaker_sdk_vs_cli_independent` -- SDK circuit open, CLI still works

### Existing test compatibility

- `DirectCompletionClient.__init__` changes (max_retries, timeout) only affect real SDK client behavior. Tests mock at `self.client.messages.create`, unaffected.
- Circuit breaker integration in api.py needs instances initialized. Test fixtures in `conftest.py` need updating to create circuit breakers.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Circuit breaker too aggressive | Medium | Medium | Default threshold=5 is generous; configurable via env vars |
| Circuit breaker too lenient | Low | Low | Monitor in Phase 3; adjust thresholds |
| Thread safety bugs | Low | High | Comprehensive concurrent tests; use Lock not RLock |
| SDK retry change masks errors | Low | Medium | Retry only applies to SDK built-in retryable errors (429, 500, connection) |
| conftest.py changes break other tests | Medium | High | Add circuit breaker to existing fixture with sensible defaults |

## Success Criteria

- [ ] SDK `max_retries` configurable, default 4
- [ ] SDK timeout configurable, default 60s
- [ ] Circuit breaker trips after 5 consecutive retryable failures
- [ ] Circuit breaker half-opens after 30s
- [ ] Circuit open returns HTTP 503 immediately (fast-fail, no upstream call)
- [ ] Non-retryable errors (auth, bad_request) do not trip circuit
- [ ] `/health` includes circuit breaker state
- [ ] All existing tests pass
- [ ] 16+ new tests added

## Dependencies

- **Phase 1 must be complete** — circuit breaker relies on `error_category` field in `TaskResult`
- No new package dependencies — uses only stdlib `threading`, `time`
