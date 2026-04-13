---
type: effort
effort_id: EFFORT-Cross-Service-Observability
project: claude-code-api-service
status: planning
priority: high
progress: 0%
created: 2026-04-11T00:00:00Z
last_updated: 2026-04-11T00:00:00Z
linked_goal: null
related_forgg_effort: EFFORT-Cross-Service-Observability (PROJECT-Forgg)
forgg_phase: 4c
forgg_cycle: 4
dependencies:
  - PROJECT-Forgg Phase 0 (forgg-observability package published)
  - PROJECT-Forgg Phase 3 (claude-agents trace context flows into CCAS)
---

# EFFORT: Cross-Service Observability (Phase 4c)

## Overview

Instrument claude-code-api-service (CCAS) with OpenTelemetry distributed tracing and structured logging as part of the Forgg platform-wide observability rollout. CCAS is Phase 4c of PROJECT-Forgg's `EFFORT-Cross-Service-Observability`, running in parallel with Phase 4a (claude-agents) and Phase 4b (ai-service) in Week 4 of the sprint.

CCAS is the LLM routing proxy between the agent runtime (claude-agents, port 8005) and LLM providers. Today, every request from claude-agents disappears into CCAS and reappears with a response — no visibility into whether the request took the SDK or CLI path, whether the subprocess started, whether the Anthropic SDK retried, where latency was spent, or whether tool passthrough preserved structure. This effort closes that blind spot by emitting a connected trace for every request on both endpoints (`/v1/process`, `/v1/chat/completions`) with spans for HTTP receive, LLM call (via OpenLLMetry), and subprocess lifecycle (CLI path).

## Why This Matters

1. **Black box between claude-agents and Anthropic.** When a conversation goes sideways, we currently cannot tell whether the problem is in claude-agents' dispatch logic, CCAS's routing, the Anthropic API, or the CLI subprocess. This effort splits that into distinct spans.
2. **Tool passthrough opacity.** `TOOL_PASSTHROUGH_ENABLED=true` means tool definitions flow through CCAS. We need to see whether tool_use content blocks came back and whether translation (OpenAI ↔ Anthropic) preserved structure.
3. **Subprocess latency attribution.** The CLI path has 3-8s cold start. A trace with `llm.cli_path.subprocess` span will show exactly how much of that is Popen spawn, subprocess execution, and CCA overhead.
4. **Retry/circuit-breaker visibility.** Our in-process EFFORT-LLM-Resilience Phase 3 built local metrics (`/health` error rates, circuit-breaker state). OTel traces will cross-reference those with specific failed conversation_ids, so we can replay a specific broken session end-to-end.

## Scope

### In Scope

- OpenTelemetry SDK initialization via `forgg-observability.init_telemetry()` at service startup
- Structured logging via `forgg-observability.setup_logging()` (replacing current `src/logging_config.py` while preserving existing field whitelist)
- `ForggLoggingMiddleware` on the FastAPI app
- FastAPI auto-instrumentation for HTTP receive spans on both `/v1/chat/completions` and `/v1/process`
- Extraction of `forgg.tenant_id` and `forgg.conversation_id` from incoming headers/payload and attachment to the parent span
- `TRACEPARENT` environment variable injection into CLI subprocess (`src/worker_pool.py:_start_task_locked`)
- Manual wrapping span `llm.sdk_path` around `DirectCompletionClient.complete()` (OpenLLMetry handles nested `gen_ai.*` spans automatically)
- Manual span `llm.cli_path.subprocess` around the Popen lifecycle in the CLI path
- Bearer token auth span attributes (`auth.method=bearer`, `auth.result=success|failure`) on the HTTP parent span
- Integration test for `run_in_executor` context propagation (asyncio → ThreadPoolExecutor → subprocess)
- Environment configuration: `OTEL_EXPORTER_OTLP_ENDPOINT`, `TRACELOOP_TRACE_CONTENT=false`, `ENVIRONMENT`, `OTEL_SAMPLING_RATIO`, `FORGG_CAPTURE_DB_STATEMENT=false` (CCAS has no DB access, but env hygiene matters)
- p99 latency regression test (<1% delta vs baseline)
- PHI/content safety verification (no prompt/completion text in any span attribute)

### Out of Scope

- The Claude Code CLI itself emitting OTel spans from inside the `claude -p` subprocess (that's Anthropic's CLI, not us). We will set `TRACEPARENT` in the subprocess env so future CLI OTel support just works, but spans from inside the subprocess are not achievable in this effort.
- WebSocket streaming path (`/v1/stream`) instrumentation — deferred unless Phase 4c exit criteria require it
- Metrics (RED — rate/errors/duration) beyond what falls out of OTel traces automatically
- Langfuse LLM-session integration (Phase 0 / Phase 6 concern, backend-side)
- Tool execution spans — those belong to claude-agents (Phase 4a), not CCAS

## Success Criteria

- [ ] `forgg-observability[fastapi,redis,llm]` installed and locked in requirements
- [ ] `init_telemetry()` and `setup_logging()` called in `main.py` lifespan before worker pool starts
- [ ] `ForggLoggingMiddleware` installed after `RequestIDMiddleware`
- [ ] HTTP receive spans appear in SigNoz for both `/v1/chat/completions` and `/v1/process` with `forgg.tenant_id` and `forgg.conversation_id` attributes (when provided by caller)
- [ ] SDK path produces a `gen_ai.*` span (via OpenLLMetry) nested inside the HTTP parent span
- [ ] CLI path produces a `llm.cli_path.subprocess` span nested inside the HTTP parent span with `subprocess.pid`, `subprocess.returncode`, `subprocess.duration_ms` attributes
- [ ] CLI subprocess environment contains `TRACEPARENT` matching the parent span (verified via integration test)
- [ ] `run_in_executor` context propagation verified — spans emitted inside executor callables attach to the correct parent
- [ ] A request from claude-agents to CCAS shows as a connected span chain in SigNoz (requires Phase 4a complete for upstream attribution)
- [ ] Structured logs include `trace_id`, `span_id`, and all 10 existing whitelisted fields (`error_category`, `upstream_status`, `retry_count`, `task_id`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `circuit_state`, `is_retryable`)
- [ ] No prompt/completion content in any span attribute (verified via SigNoz query)
- [ ] Bearer auth spans show `auth.method=bearer` + success/failure result
- [ ] p99 latency delta <1% vs pre-instrumentation baseline (measured over 100 requests per endpoint per path)
- [ ] Existing test suite passes (no regressions)

## Affected Files

| File | Lines (approx) | Change |
|------|----------------|--------|
| `requirements.txt` | +1 | Add `forgg-observability[fastapi,redis,llm]` |
| `main.py` | ~60-120 | Add `init_telemetry()` + `setup_logging()` in lifespan; add `ForggLoggingMiddleware` |
| `src/logging_config.py` | full file review | Swap for `forgg_observability.setup_logging()` while preserving field whitelist; may become a thin wrapper or be removed |
| `src/api.py` | 246-260, 647-690 | Extract `forgg.tenant_id` / `forgg.conversation_id` from request; attach to current span |
| `src/worker_pool.py` | 469-493 (`_start_task_locked`) | Inject `TRACEPARENT` into env dict; wrap Popen in manual span `llm.cli_path.subprocess` |
| `src/direct_completion.py` | 72-209 (`complete`) | Wrap method in manual span `llm.sdk_path` for tenant/conversation attributes; verify OpenLLMetry auto-instruments `messages.create` |
| `src/auth.py` | TBD | Add span attributes `auth.method=bearer`, `auth.result` |
| `src/settings.py` | +5 | Read OTel/forgg-observability env vars |
| `tests/test_trace_propagation.py` | new | Integration test for `run_in_executor` → subprocess `TRACEPARENT` propagation |
| `tests/test_latency_budget.py` | new | p99 delta regression test |

## Known Risks

1. **`run_in_executor` context propagation (HIGH).** Both endpoints wrap blocking calls in `loop.run_in_executor(None, ...)`. Python OTel uses `contextvars.ContextVar`, which do not automatically propagate across the asyncio → default ThreadPoolExecutor boundary. If `forgg-observability` does not transparently handle this, spans emitted from inside the executor callable will have no parent and silently break the trace. **Mitigation:** verify behavior in Phase 0 library; if missing, either (a) ask FORGG to patch `forgg-observability`, or (b) write a local wrapper using `contextvars.copy_context().run(fn, *args)` and route all `run_in_executor` calls through it.

2. **Monitor thread GIL contention regression (MEDIUM).** EFFORT-Health-Endpoint-Deadlock shipped a fix where the `WorkerPool._monitor_loop` daemon thread contended with uvloop's idle callback, causing a process hang. Fix: force `loop="asyncio"` and reduce poll rate to 2Hz. **Mitigation:** Phase 4c MUST NOT instrument `_monitor_loop` in any way that adds lock contention. Explicit non-goal documented in PR description.

3. **Anthropic SDK version skew vs `opentelemetry-instrumentation-anthropic` (LOW).** CCAS pins `anthropic` to a specific version for reproducibility. OpenLLMetry has its own compatibility matrix. **Mitigation:** 10-minute compat check at Phase 0 handoff; coordinate a version bump with FORGG if needed.

4. **PHI leakage via structured content blocks (MEDIUM).** `DirectCompletionClient.complete()` extracts `tool_use` content blocks from Anthropic responses. If we accidentally attach these as span attributes, prompts/tool arguments could leak. **Mitigation:** `TRACELOOP_TRACE_CONTENT=false` as a default; rely on `forgg-observability` allowlist (Contract 4) as a second layer; explicit PR reviewer checklist item.

5. **Subprocess OTel spans are unreachable today (LOW, already flagged to FORGG).** The CLI subprocess is `claude -p`, Anthropic's CLI. It does not emit OTel. `TRACEPARENT` injection is cosmetic until that changes. **Mitigation:** accept relaxed exit criterion from FORGG (env var present, not child spans visible).

## Dependencies

**From PROJECT-Forgg (upstream):**
- Phase 0 complete — `forgg-observability` package pip-installable, SigNoz running, OTel Collector reachable
- Phase 3 complete — goal-orchestrator-bridge propagates trace context across the Redis Streams boundary, so upstream traces can connect to CCAS spans (otherwise CCAS spans are orphan roots)
- FORGG response to clarifying questions in MSG-CCA-20260411-001:
  - Confirmation of relaxed subprocess-span exit criterion
  - `run_in_executor` context propagation helper (built into library, OR documented pattern)
  - `allowed_extra_fields` parameter on `setup_logging()` to preserve the 10-field whitelist
  - Header convention for `forgg.conversation_id` (coordinated with Phase 4a)

**From CCAS to downstream:**
- None. Phase 4a (claude-agents) and Phase 4b (ai-service) are parallel — they do not depend on CCAS completion.

## Related Efforts

- **EFFORT-LLM-Resilience** (completed) — built local error tracker, `/health` enrichment, and structured log field whitelist. Complementary to this effort. The field whitelist must be preserved when swapping to `forgg_observability.setup_logging()`.
- **EFFORT-Subprocess-Env-Hygiene** (completed) — established the pattern of explicit subprocess env construction in `WorkerPool._start_task_locked`. This effort extends it by adding `TRACEPARENT` injection.
- **EFFORT-Health-Endpoint-Deadlock** (completed) — cautionary precedent. Any OTel instrumentation of the monitor thread path risks regressing the fix. Explicit non-goal.
- **EFFORT-Production-Hardening** (completed) — established health/logging infrastructure this effort builds upon.

## References

- **FORGG proposal:** `~/Forgg/INBOX/archive/MSG-FRG-20260410-006-to-CCA.md` (or wherever FORGG archives it)
- **CCA response to FORGG:** `~/Forgg/INBOX/MSG-CCA-20260411-001-to-FRG.md` (source: `OUTBOX/MSG-CCA-20260411-001-to-FRG.md`)
- **FORGG master plan:** `~/Forgg/EFFORT-Cross-Service-Observability/PLAN.md`
- **FORGG research synthesis:** `~/Forgg/EFFORT-Cross-Service-Observability/research/RESEARCH-SYNTHESIS.md`
- **FORGG research — subprocess patterns:** `~/Forgg/EFFORT-Cross-Service-Observability/research/RESEARCH-trace-propagation-async.md`
- **Coordination protocol:** `~/Forgg/COORDINATION-PROTOCOL.md`

## Plan Documents

- [[PLAN-Phase-4c-Instrumentation]] — preliminary work plan (this effort)

## Status

**2026-04-11:** Effort created. Preliminary plan drafted. Awaiting FORGG response to clarifying questions (see §6 of MSG-CCA-20260411-001) and formal go-signal to begin work. Execution is blocked on Phase 0 shipping `forgg-observability` to a pip-installable location and on Phase 3 closing the Redis Streams trace gap upstream.
