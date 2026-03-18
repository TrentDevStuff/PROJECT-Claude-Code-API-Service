---
type: effort
effort_id: EFFORT-LLM-Resilience
project: PROJECT-Claude-Code-API-Service
status: in_progress
priority: high
progress: 100%
created: 2026-03-18T10:00:00Z
last_updated: 2026-03-18T11:30:00Z
linked_goal: null
---

# EFFORT: LLM Proxy Resilience

## Overview

Fix intermittent LLM proxy 500 errors in the claude-code-api-service. When the upstream Anthropic API fails (rate limits, overload, transient errors), our service returns unhelpful HTTP 500s to callers with no retry guidance, no error differentiation, and no observability into failure patterns.

The service has two execution paths — SDK direct (`src/direct_completion.py`) and CLI subprocess (`src/worker_pool.py`) — both of which need error handling improvements.

## Root Causes

1. **No retry differentiation** — `direct_completion.py` catches all `anthropic.APIError` uniformly, returns FAILED. SDK default is only 2 retries.
2. **Wrong HTTP status codes** — Upstream Anthropic 429/529/500 all surface as HTTP 500 from our service. Callers cannot distinguish retryable from permanent failures.
3. **CLI path opacity** — When CLI subprocess fails due to upstream API issues, error messages are opaque (just exit code + stderr dump).
4. **No circuit breaker** — Repeated upstream failures cascade. No backoff or circuit breaking to protect the service.

## Phased Approach

| Phase | Scope | Risk | Ship Target |
|-------|-------|------|-------------|
| Phase 1 | Error classification + HTTP status codes | Low | Immediate |
| Phase 2 | Retry logic + circuit breaker | Medium | +2-3 days |
| Phase 3 | Observability + metrics | Low | +1-2 days |

## Scope

### In Scope

- Error classification for both SDK and CLI paths
- Correct HTTP status code mapping (429, 502, 503, 504)
- Enhanced retry logic with exponential backoff for SDK path
- Circuit breaker for upstream API protection
- Error rate tracking and structured logging
- Retry-After header propagation

### Out of Scope

- Prometheus/Grafana dashboards (future effort)
- Client-side retry logic in `client/` SDK
- Failover to alternative LLM providers
- WebSocket path error handling (separate effort)

## Success Criteria

- [ ] Upstream 429 returns HTTP 429 with Retry-After header
- [ ] Upstream 500/529 returns HTTP 502 (Bad Gateway)
- [ ] Upstream timeout returns HTTP 504 (Gateway Timeout)
- [ ] SDK path retries transient errors up to 4 times with exponential backoff
- [ ] Circuit breaker trips after 5 consecutive failures, half-opens after 30s
- [ ] Error logs include `upstream_status`, `error_category`, `is_retryable` fields
- [ ] All 228+ existing tests pass, 80%+ coverage maintained
- [ ] New tests cover each error classification path

## Plan Documents

- [[PLAN-LLM-Resilience]] — High-level phased overview
- [[PLAN-Phase-1-Error-Classification]] — Detailed Phase 1
- [[PLAN-Phase-2-Retry-Resilience]] — Detailed Phase 2
- [[PLAN-Phase-3-Observability]] — Detailed Phase 3

## Related

- EFFORT-Production-Hardening (established health/logging infrastructure we build upon)
- EFFORT-Subprocess-Env-Hygiene (recent CLI subprocess fixes)
