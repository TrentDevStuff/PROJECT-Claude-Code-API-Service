---
created: 2026-04-18T00:00:00Z
updated: 2026-04-18T00:00:00Z
type: findings
effort: EFFORT-Cross-Service-Observability
status: step-1-shipped-with-known-gap
---

# Step 1 Findings — telemetry init wired, structured-output bridge deferred

Phase 4c Step 1 (per `PLAN-Phase-4c-Instrumentation.md`) shipped on
`feature/phase-4c-instrumentation` against forgg-observability v0.3.0
ahead of the original 2026-04-28 schedule.

## What landed

- `forgg-observability[fastapi,redis,llm]>=0.3.0,<0.4.0` added to
  `pyproject.toml` dependencies. Installed editable from
  `/Users/trent/PROJECT-Forgg-Observability` for dev.
- `init_telemetry()` called at the top of `main.py::lifespan()`,
  immediately after the `CLAUDECODE` env-var strip and before any service
  initialization. CCA disables `enable_asyncpg / enable_psycopg /
  enable_pymongo` (no Postgres / no Mongo) to suppress the v0.3.0 loud
  banner for connectors we don't use.
- `setup_logging()` called immediately after `init_telemetry()`, with
  CCA's existing 26-field whitelist (renamed to `ALLOWED_EXTRA_LOG_FIELDS`
  module constant) passed through as `allowed_extra_fields`.
- `ForggLoggingMiddleware` inserted between `RequestIDMiddleware`
  (innermost) and `CORSMiddleware` (outermost). On every request it
  binds `path`, `method`, `request_id`, and (when present)
  `conversation_id`/`tenant_id` to structlog contextvars and span
  attributes.
- Old `src/logging_config.py` deleted. Only `main.py` imported it, so
  removal is clean. `JSONFormatter` is no longer needed — structlog +
  `forgg_observability.setup_logging` replace it.

## Acceptance signal — partial

The PLAN's Step 1 acceptance is "service starts successfully + `/health`
emits a structured log line containing `service.name` + `trace_id` +
existing whitelist preserved." Status:

| Criterion | Status |
|---|---|
| Service starts successfully | ✅ Yes — uvicorn boots, `/health` returns 200, all 325 tests pass |
| `service.name=claude-code-api-service` on log lines | ⚠️ Only on structlog calls — see below |
| `trace_id` propagation | ⚠️ Same — structlog only |
| Existing field whitelist preserved | ✅ Passed via `allowed_extra_fields` |

## The gap — stdlib loggers don't flow through structlog

`forgg_observability.setup_logging()` configures structlog's pipeline
(`service_name`, OTel context injection, allowlist warner) but calls
`logging.basicConfig(format="%(message)s", force=True)` for stdlib's
root handler. That stdlib handler does NOT use structlog's
`ProcessorFormatter`, so any code calling `logging.getLogger(__name__)`
gets bare `%(message)s` output — no `service.name`, no `trace_id`, no
contextvar enrichment.

CCA emits ~all of its log lines via stdlib (`logger.info(...)` calls
across `src/api.py`, `src/worker_pool.py`, `src/middleware.py`, etc.).
None of those will produce structured output until either:

1. **forgg-observability adds a stdlib bridge** — install a stdlib
   `Handler` with `structlog.stdlib.ProcessorFormatter` so stdlib
   `LogRecord` objects flow through the same pipeline as native
   structlog calls. ~10 lines in `setup_logging()`. Backwards-compatible.
2. **CCA migrates its loggers to structlog** — replace
   `logger = logging.getLogger(__name__)` with
   `logger = structlog.get_logger(__name__)`. Larger blast radius
   (~30+ call sites), and many callers pass `extra={...}` which uses
   stdlib semantics structlog treats differently.

**Recommended path:** option 1. The bridge belongs in the library so
every Forgg consumer gets it for free. Will raise with FRG before
Phase 4c PR.

This gap doesn't block Step 2 (extract tenant/conversation attributes
on incoming requests) or Step 3 (span around `_chat_completion_with_tools`),
because both produce structlog-native output. It only affects the
*existing* CCA log call sites' enrichment.

## v0.3.0 install verification

`forgg-observability check` in CCA venv (post-install):

```
Core dependencies                    OK (8/8)
Optional instrumentors enabled       OK (4/4: fastapi, httpx, redis, anthropic)
Optional instrumentors not installed openai, google_generativeai
                                     (CCA does not use these — accepted)
Optional connectors not enabled      asyncpg, psycopg, pymongo, logging
                                     (CCA disables via init_telemetry kwargs)
```

The `openai` / `google_generativeai` warnings still fire at startup
because the `[llm]` extra enables ALL LLM instrumentors, and v0.3.0's
"loud banner" finding lists every package that's enabled-but-missing.
Cosmetic noise; no functional impact.

## ALLOWED_SPAN_ATTRIBUTES alignment

Confirmed with `forgg-observability` v0.3.0 that the cache attrs from
`NOTE-Phase-4c-Attribute-Naming-Guidance.md` are present in the
allowlist as expected:

- `gen_ai.usage.cache_creation.input_tokens` ✅
- `gen_ai.usage.cache_read.input_tokens` ✅
- `gen_ai.usage.input_tokens` / `output_tokens` / `total_tokens` ✅
- `gen_ai.usage.cache_hit_ratio` — **not present** (matches "drop ratio,
  compute in SigNoz" decision) ✅

ACA Contract 4 alignment satisfied at the library level. No additional
coordination needed before Phase 4c PR.

## Open questions for FRG (defer until PR review)

1. Should `setup_logging()` install a stdlib→structlog bridge so
   existing service code gets enrichment for free? (Affects every
   service that hasn't migrated to structlog yet — not just CCA.)
2. Per-LLM `enable_anthropic` / `enable_openai` / `enable_google` flags
   on `init_telemetry()` to silence the loud banner for unused providers?
   v0.4.0 nice-to-have.
