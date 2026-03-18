---
created: 2026-03-18T10:00:00Z
updated: 2026-03-18T10:00:00Z
type: plan
backlinks: []
---

# PLAN: Phase 3 — Observability

## Overview

Add error tracking, structured log fields, and operational visibility so that error patterns can be detected and diagnosed without digging through raw logs. Builds on Phase 1's error classification to provide aggregated views.

## Scope

1. **Structured error logging** — add error classification fields to JSON log output
2. **Error rate counters** — in-memory sliding window counters by error category
3. **Health endpoint enrichment** — expose error rates and circuit breaker state in `/health`
4. **Response headers** — add debugging headers to error responses

## Files Changed

### 1. `src/logging_config.py` — Expand structured log fields

**What changes:**
- Add error-specific fields to the `JSONFormatter.format()` field whitelist

**New fields to whitelist:**
```python
"error_category", "upstream_status", "is_retryable",
"circuit_state", "retry_count", "task_id",
"model", "latency_ms", "input_tokens", "output_tokens",
```

This is purely additive — existing log calls without these fields are unaffected.

### 2. New file: `src/error_tracker.py` — Sliding window error counter

**Design:** Lightweight in-memory counter tracking error occurrences in a sliding window (default: 5 minutes). No external dependencies.

**Interface:**
```python
class ErrorTracker:
    def __init__(self, window_seconds: float = 300.0):
        ...

    def record(self, category: str, path: str = "sdk") -> None:
        """Record an error occurrence."""

    def rates(self) -> dict[str, dict[str, int]]:
        """Return error counts by category and path within the window.
        Example: {"sdk": {"rate_limited": 3, "timeout": 1}, "cli": {"cli_error": 2}}
        """

    def total_errors(self) -> int:
        """Total errors in current window."""

    def summary(self) -> dict:
        """Summary dict for health endpoint."""
```

**Implementation:** `collections.deque` with timestamped entries. On each `rates()` call, prune entries older than the window. Thread-safe via `threading.Lock`.

**Why not Redis/external storage:** Operational telemetry for a single-instance service. In-memory is simpler, faster, and ephemeral by nature.

### 3. `src/api.py` — Record errors and add response headers

**What changes:**

At each failure point, before raising HTTPException:
```python
if result.status != TaskStatus.COMPLETED:
    if error_tracker and result.error_category:
        error_tracker.record(result.error_category, path="sdk")
    _raise_for_failed_task(result)
```

**Response headers on errors (in `_raise_for_failed_task` helper):**
```python
headers = {}
if result.retry_after:
    headers["Retry-After"] = str(int(result.retry_after))
if result.error_category:
    headers["X-Error-Category"] = result.error_category
if result.upstream_status:
    headers["X-Upstream-Status"] = str(result.upstream_status)
```

### 4. `src/direct_completion.py` — Enriched error logging

**What changes:**
- Each `except` block logs with structured fields:

```python
except anthropic.RateLimitError as e:
    logger.warning(
        "Anthropic rate limit hit",
        extra={
            "error_category": "rate_limited",
            "upstream_status": 429,
            "is_retryable": True,
            "model": model_id,
        },
    )
```

- `logger.warning` for retryable errors, `logger.error` for non-retryable

### 5. `main.py` — Health endpoint enrichment

**What changes:**
- Create `ErrorTracker` instance in lifespan
- Pass to `initialize_services()` (extend the function signature)
- Add to `/health` response:

```python
if error_tracker:
    svc["error_rates"] = ServiceHealth(
        status="ok" if error_tracker.total_errors() < 50 else "degraded",
        detail=error_tracker.summary(),
    )

if sdk_circuit:
    svc["sdk_circuit_breaker"] = ServiceHealth(
        status="ok" if sdk_circuit.state == "closed" else "degraded",
        detail=sdk_circuit.status(),
    )
```

### 6. `src/worker_pool.py` — Enhanced failure logging

**What changes:**
- In `_process_completed_task`, log failures with structured fields:

```python
logger.error(
    "CLI task failed",
    extra={
        "task_id": task_id[:8],
        "error_category": task.result.error_category,
        "returncode": returncode,
        "model": task.model,
    },
)
```

## Implementation Steps

1. Create `src/error_tracker.py` -- standalone, no dependencies
2. Write `tests/test_error_tracker.py` -- window pruning, thread safety, summary format
3. Update `src/logging_config.py` -- expand field whitelist
4. Update `src/direct_completion.py` -- enriched error log lines
5. Update `src/worker_pool.py` -- enriched failure log lines
6. Update `src/api.py` -- error tracking calls, response headers
7. Update `main.py` -- error tracker lifecycle, health endpoint
8. Run full test suite

## Test Strategy

### New tests: `tests/test_error_tracker.py` (~8 tests)

- `test_record_and_rates` -- basic record + retrieve
- `test_window_expiry` -- old entries pruned after window
- `test_multiple_categories` -- separate counting per category
- `test_multiple_paths` -- separate counting per path (sdk/cli)
- `test_total_errors` -- aggregate count
- `test_summary_format` -- verify dict structure
- `test_thread_safety` -- concurrent record calls
- `test_empty_tracker` -- rates() and summary() with no data

### Updated tests

- `tests/test_api.py`: verify `X-Error-Category` and `X-Upstream-Status` headers on error responses (~2 tests)
- Health tests: verify error_rates appears in `/health` response

### Existing test compatibility

- `logging_config.py` changes are additive (extra field whitelist). No existing tests assert on specific log output format.
- `main.py` health endpoint adds new service entries. Existing health tests assert on structure, not specific service names, so should pass.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Memory growth from error_tracker | Very Low | Low | Deque with time-based pruning; 5-min window caps entries |
| Health endpoint format breaks callers | Low | Medium | Additive -- new keys only, existing keys unchanged |
| Log volume increase | Low | Low | Only error paths get new fields; success paths unchanged |
| X-Error-Category header leaks info | Very Low | Low | Generic categories only, no stack traces |

## Success Criteria

- [ ] Error logs include `error_category`, `upstream_status`, `is_retryable` fields
- [ ] `/health` shows error rates by category (last 5 minutes)
- [ ] `/health` shows circuit breaker state (from Phase 2)
- [ ] Error responses include `X-Error-Category` header
- [ ] Error responses include `X-Upstream-Status` header when available
- [ ] Error responses include `Retry-After` when available
- [ ] All existing tests pass
- [ ] 10+ new tests added
- [ ] No new package dependencies

## Dependencies

- **Phase 1 must be complete** — relies on `error_category` field in `TaskResult`
- **Phase 2 is optional** — circuit breaker status in `/health` is nice-to-have; error tracking works without it
- No new package dependencies
