---
created: 2026-03-18T10:00:00Z
updated: 2026-03-18T10:00:00Z
type: plan
backlinks: []
---

# PLAN: Phase 1 — Error Classification

## Overview

Correct the HTTP status codes returned when upstream Anthropic API calls fail. Currently all failures return HTTP 500. After this phase, callers receive semantically correct status codes that tell them whether to retry, back off, or report a bug.

## Error Category Taxonomy

| Upstream Condition | SDK Exception | Error Category | Our HTTP Status | Retryable? |
|-------------------|---------------|---------------|----------------|------------|
| Rate limited (429) | `anthropic.RateLimitError` | `rate_limited` | 429 | Yes (with Retry-After) |
| Overloaded (529) | `anthropic.InternalServerError` (status=529) | `overloaded` | 503 | Yes (backoff) |
| Server error (500) | `anthropic.InternalServerError` (status=500) | `upstream_error` | 502 | Yes (limited) |
| Auth error (401/403) | `anthropic.AuthenticationError` | `auth_error` | 502 | No |
| Bad request (400) | `anthropic.BadRequestError` | `bad_request` | 400 | No |
| Timeout | `anthropic.APITimeoutError` | `timeout` | 504 | Yes |
| Connection error | `anthropic.APIConnectionError` | `connection_error` | 502 | Yes |
| CLI exit code != 0 | N/A (subprocess) | `cli_error` | 502 | Depends on stderr |
| CLI timeout | N/A (subprocess) | `timeout` | 504 | Yes |
| Unknown | `Exception` | `internal_error` | 500 | No |

## Files Changed

### 1. `src/worker_pool.py` — Add error metadata to TaskResult

**What changes:**
- Add optional `error_category: str`, `upstream_status: int | None`, and `retry_after: float | None` fields to the `TaskResult` dataclass
- These are purely additive fields with defaults of `None`, so all existing code that creates `TaskResult` objects continues to work unchanged
- In `_process_completed_task`, when `returncode != 0`, scan stderr for known patterns to classify errors

**TaskResult additions:**
```python
@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    completion: str | None = None
    usage: dict[str, int] | None = None
    cost: float | None = None
    error: str | None = None
    # Phase 1: error classification
    error_category: str | None = None       # e.g. "rate_limited", "overloaded", "timeout"
    upstream_status: int | None = None       # e.g. 429, 529, 500
    retry_after: float | None = None         # seconds, from Retry-After header
```

**CLI stderr pattern matching in `_process_completed_task`:**
- `"rate limit"` or `"429"` --> `error_category="rate_limited"`
- `"overloaded"` or `"529"` --> `error_category="overloaded"`
- `"server error"` or `"500"` --> `error_category="upstream_error"`
- `"timed out"` or `"timeout"` --> `error_category="timeout"`
- Default --> `error_category="cli_error"`

### 2. `src/direct_completion.py` — Granular exception handling

**What changes:**
- Replace the single `except anthropic.APIError` block with specific exception handlers
- Each handler sets `error_category`, `upstream_status`, and `retry_after` on the returned `TaskResult`

**Exception handler order:**
```python
except anthropic.RateLimitError as e:
    # Extract Retry-After header if present
    retry_after = None
    if hasattr(e, 'response') and e.response is not None:
        retry_after_val = e.response.headers.get("retry-after")
        if retry_after_val:
            try:
                retry_after = float(retry_after_val)
            except (ValueError, TypeError):
                pass
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Rate limited by Anthropic API: {e}",
        error_category="rate_limited", upstream_status=429,
        retry_after=retry_after,
    )

except anthropic.InternalServerError as e:
    status_code = getattr(e, 'status_code', 500)
    category = "overloaded" if status_code == 529 else "upstream_error"
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Anthropic server error ({status_code}): {e}",
        error_category=category, upstream_status=status_code,
    )

except anthropic.APITimeoutError as e:
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Anthropic API timeout: {e}",
        error_category="timeout",
    )

except anthropic.APIConnectionError as e:
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Anthropic API connection error: {e}",
        error_category="connection_error",
    )

except anthropic.AuthenticationError as e:
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Anthropic auth error: {e}",
        error_category="auth_error", upstream_status=401,
    )

except anthropic.BadRequestError as e:
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Bad request to Anthropic API: {e}",
        error_category="bad_request", upstream_status=400,
    )

except anthropic.APIError as e:
    # Catch-all for any other API errors
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Anthropic API error: {e}",
        error_category="upstream_error",
    )

except Exception as e:
    # Non-API errors (network, parsing, etc.)
    return TaskResult(
        task_id="sdk-direct", status=TaskStatus.FAILED,
        error=f"Direct completion error: {e}",
        error_category="internal_error",
    )
```

### 3. `src/api.py` — Map error categories to HTTP status codes

**What changes:**
- Add `_raise_for_failed_task()` helper function
- Replace the four places where `HTTPException(500, ...)` is raised for task failures

**The four failure points:**
1. Line 244 (`chat_completion`): `raise HTTPException(status_code=500, ...)`
2. Line 578 (`process_ai_services_compatible`, SDK path): `raise HTTPException(500, ...)`
3. Line 617 (`process_ai_services_compatible`, CLI path): `raise HTTPException(504 if ... else 500, ...)`
4. Line 339 (batch processing): implicit 500 via `status="failed"`

**Helper function:**
```python
_ERROR_HTTP_MAP = {
    "rate_limited": 429,
    "overloaded": 503,
    "upstream_error": 502,
    "auth_error": 502,
    "timeout": 504,
    "connection_error": 502,
    "bad_request": 400,
    "cli_error": 502,
    "internal_error": 500,
}

def _raise_for_failed_task(result: TaskResult) -> None:
    """Raise HTTPException with correct status code based on error category."""
    if result.status == TaskStatus.TIMEOUT:
        status = 504
    elif result.error_category:
        status = _ERROR_HTTP_MAP.get(result.error_category, 500)
    else:
        status = 500

    headers = {}
    if result.retry_after:
        headers["Retry-After"] = str(int(result.retry_after))

    raise HTTPException(
        status_code=status,
        detail=result.error or "Unknown error",
        headers=headers or None,
    )
```

## Implementation Steps

1. Add fields to `TaskResult` in `src/worker_pool.py` (3 optional fields, backward compatible)
2. Run tests -- verify all 228 pass with no changes
3. Update `src/direct_completion.py` -- granular exception handling
4. Add new tests for each SDK error path in `tests/test_direct_completion.py`
5. Update `src/worker_pool.py` `_process_completed_task` -- stderr pattern matching
6. Add new tests for CLI error classification in `tests/test_worker_pool.py`
7. Update `src/api.py` -- add helper, replace 4 failure points
8. Add new tests for HTTP status code mapping in `tests/test_api.py`
9. Run full test suite -- all tests pass, coverage maintained

## Test Strategy

### Existing tests (must not break)

The key risk is the `TaskResult` dataclass change. Since we add optional fields with defaults, all existing constructions like `TaskResult(task_id=..., status=..., error=...)` remain valid.

### New tests to add

**`tests/test_direct_completion.py`** (new file, ~8 tests):
- `test_rate_limit_error_classification` -- mock `anthropic.RateLimitError`, verify `error_category="rate_limited"`, `upstream_status=429`
- `test_rate_limit_retry_after_extraction` -- mock with Retry-After header
- `test_overloaded_529_classification` -- mock `InternalServerError` with status 529
- `test_server_error_500_classification` -- mock `InternalServerError` with status 500
- `test_timeout_error_classification` -- mock `APITimeoutError`
- `test_connection_error_classification` -- mock `APIConnectionError`
- `test_auth_error_classification` -- mock `AuthenticationError`
- `test_bad_request_classification` -- mock `BadRequestError`

**`tests/test_worker_pool.py`** (additions, ~4 tests):
- `test_cli_rate_limit_stderr_detection` -- mock process with "rate limit" in stderr
- `test_cli_overloaded_stderr_detection` -- mock process with "overloaded" in stderr
- `test_cli_timeout_stderr_detection` -- mock process with "timed out" in stderr
- `test_cli_unknown_error_fallback` -- mock process with unrecognized stderr

**`tests/test_api.py`** (additions, ~5 tests):
- `test_process_rate_limit_returns_429` -- SDK path returns rate_limited category
- `test_process_overload_returns_503` -- SDK path returns overloaded category
- `test_process_upstream_error_returns_502` -- SDK path returns upstream_error
- `test_process_timeout_returns_504` -- SDK path returns timeout
- `test_retry_after_header_propagated` -- verify Retry-After header in response

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TaskResult field additions break tests | Very Low | High | Optional fields with defaults; run tests after step 1 |
| stderr pattern matching false positives | Low | Low | Patterns are conservative; fallback is generic cli_error |
| HTTPException headers kwarg compatibility | Very Low | Medium | FastAPI HTTPException supports headers since v0.95+ |
| Anthropic SDK version differences | Low | Medium | Pin via requirements.txt; error classes exist since anthropic v0.18+ |

## Success Criteria

- [ ] Upstream 429 --> HTTP 429 with Retry-After header
- [ ] Upstream 529 --> HTTP 503
- [ ] Upstream 500 --> HTTP 502
- [ ] SDK timeout --> HTTP 504
- [ ] CLI timeout --> HTTP 504 (already partially working)
- [ ] Auth errors --> HTTP 502 (not 500)
- [ ] Bad requests --> HTTP 400 (not 500)
- [ ] All 228+ existing tests pass
- [ ] 15+ new tests added
- [ ] Coverage stays above 80%

## Dependencies

- None. No new package dependencies.
- Requires Anthropic Python SDK (already installed) which provides the specific exception classes.
