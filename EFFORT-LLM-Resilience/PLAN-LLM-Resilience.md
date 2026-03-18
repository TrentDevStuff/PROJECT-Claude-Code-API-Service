---
created: 2026-03-18T10:00:00Z
updated: 2026-03-18T10:00:00Z
type: plan
backlinks: []
---

# PLAN: LLM Proxy Resilience

## Problem Statement

The claude-code-api-service returns HTTP 500 for all upstream Anthropic API failures — rate limits (429), overload (529), transient server errors (500), and timeouts alike. Callers receive no signal about whether to retry, back off, or give up. The SDK path (`direct_completion.py`) catches `anthropic.APIError` uniformly and the CLI path (`worker_pool.py`) only sees subprocess exit codes.

## Architecture Context

```
Caller --> /v1/process --> api.py
                            |-- SDK path --> DirectCompletionClient.complete()
                            |                 \-- anthropic.Anthropic().messages.create()
                            |                      \-- Anthropic API (can return 429, 500, 529)
                            \-- CLI path --> WorkerPool.submit() --> claude CLI subprocess
                                              \-- Popen("claude -p ...") --> exit code + stderr
```

**Key insight:** Both paths funnel through `TaskResult` with `TaskStatus.FAILED`, which api.py then converts to HTTP 500. The fix requires:
1. Enriching `TaskResult` with error classification metadata
2. Teaching api.py to map error categories to correct HTTP status codes
3. Adding retry logic before failures reach `TaskResult`

## Phase Overview

### Phase 1: Error Classification (Low Risk, Ship Immediately)

**Goal:** Correct HTTP status codes, zero behavior change for successful requests.

- Classify Anthropic SDK errors by type (rate limit, overload, auth, bad request, timeout)
- Add `error_category` and `upstream_status` fields to `TaskResult`
- Map error categories to HTTP 429/502/503/504 in api.py
- Parse CLI stderr for known Anthropic error patterns
- Add Retry-After header when upstream provides one

**Files:** `src/direct_completion.py`, `src/worker_pool.py`, `src/api.py`

### Phase 2: Retry and Resilience (Medium Risk)

**Goal:** Automatically recover from transient upstream failures.

- Increase SDK client `max_retries` from 2 to 4 with backoff
- Add application-level retry for specific error categories
- Implement circuit breaker to prevent cascade failures
- Add jitter to retry timing

**Files:** `src/direct_completion.py`, `src/api.py`, new `src/circuit_breaker.py`

### Phase 3: Observability (Low Risk)

**Goal:** Track error patterns for operational awareness.

- Add structured error fields to JSON logs
- Implement in-memory error rate counters
- Expose error stats in `/health` endpoint
- Add `X-Upstream-Status` response header for debugging

**Files:** `src/logging_config.py`, `main.py`, `src/api.py`

## Dependency Graph

```
Phase 1 (error classification)
    |---> Phase 2 (retry logic depends on error categories)
    \---> Phase 3 (observability depends on error categories)
```

Phase 2 and Phase 3 are independent of each other but both depend on Phase 1.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing tests | Medium | High | Run full suite after each file change |
| Retry storms overwhelming upstream | Low | High | Circuit breaker (Phase 2), jitter |
| Over-classifying errors as retryable | Low | Medium | Conservative: only 429 and 529 are retryable |
| CLI stderr parsing breaks on CLI update | Medium | Low | Fallback to generic FAILED if pattern unrecognized |
