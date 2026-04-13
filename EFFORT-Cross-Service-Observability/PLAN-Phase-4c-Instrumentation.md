---
created: 2026-04-11T00:00:00Z
updated: 2026-04-11T00:00:00Z
type: plan
effort: EFFORT-Cross-Service-Observability
status: draft-awaiting-forgg-response
---

# PLAN: Phase 4c — CCAS Instrumentation

**Status:** DRAFT. Awaiting FORGG response to clarifying questions in MSG-CCA-20260411-001 and formal go-signal.

## Sequencing

This plan is written under the assumption that Phase 0 (FORGG infrastructure + `forgg-observability` library) is complete and Phase 3 (goal-orchestrator-bridge Redis Streams trace closure) has shipped. If either is incomplete, Phase 4c execution pauses.

Work is organized into **six steps** that should be executed **in order**. Each step has a concrete acceptance signal. Steps 1-4 are code changes; step 5 is test writing; step 6 is validation in SigNoz.

## Step 1 — Dependency + Startup Wiring

**Goal:** `forgg-observability` initialized before any FastAPI route handlers exist.

**Changes:**

1. Add to `requirements.txt`:
   ```
   forgg-observability[fastapi,redis,llm]==<pinned>
   ```
   Pin to whatever version FORGG publishes in Phase 0. Coordinate version with FORGG — see Risk 3 in EFFORT.md regarding anthropic SDK compat matrix.

2. Edit `main.py` lifespan function at the top (before `worker_pool.start()`):

   ```python
   from forgg_observability import init_telemetry, setup_logging

   async def lifespan(app: FastAPI):
       # ... existing _start_time, _shutting_down setup ...

       # Strip env vars that break Claude CLI subprocesses (unchanged)
       for _var in ("CLAUDECODE", "CLAUDE_CODE_SESSION"):
           os.environ.pop(_var, None)

       # NEW: Initialize OTel + structured logging BEFORE any other service
       init_telemetry(
           service_name="claude-code-api-service",
           service_version=app.version,
           environment=os.getenv("ENVIRONMENT", "development"),
       )
       setup_logging(
           service_name="claude-code-api-service",
           allowed_extra_fields=[
               "error_category", "upstream_status", "is_retryable",
               "circuit_state", "retry_count", "task_id",
               "model", "latency_ms", "input_tokens", "output_tokens",
               "overhead_ms", "has_tool_use", "tool_name", "tool_id",
           ],
       )

       # ... rest of existing lifespan: worker_pool.start(), budget_manager init, etc.
   ```

3. Edit `main.py` middleware section:

   ```python
   from forgg_observability.middleware.fastapi import ForggLoggingMiddleware

   # Order matters: RequestID first (existing), then Forgg logging middleware,
   # then CORS. ForggLoggingMiddleware needs request_id available.
   app.add_middleware(RequestIDMiddleware)
   app.add_middleware(ForggLoggingMiddleware)
   app.add_middleware(CORSMiddleware, ...)  # existing
   ```

**DEPENDS ON:** FORGG confirming `setup_logging()` supports `allowed_extra_fields` parameter. If not supported, either (a) pass through a subclassed formatter, or (b) file a FORGG issue and accept reduced local observability until patched.

**Acceptance signal:** Service starts successfully. A test request to `/health` produces a structured log line containing `service.name=claude-code-api-service`, `trace_id`, and the existing field whitelist remains recognized.

## Step 2 — Extract tenant/conversation attributes on incoming requests

**Goal:** every incoming HTTP request has `forgg.tenant_id` and `forgg.conversation_id` set on the parent span (when provided by caller).

**Decision point:** how does claude-agents propagate conversation_id to CCAS? Three options:

- **Option A:** HTTP header `X-Forgg-Conversation-Id` + `X-Forgg-Tenant-Id`. Simplest. Middleware-level extraction possible.
- **Option B:** Payload field on `ProcessRequest` and `ChatCompletionRequest`. More explicit, but requires schema changes on both sides.
- **Option C:** Inferred from existing fields (`project_id` → tenant). No new contract, but loses conversation scope.

**Recommendation:** Option A for conversation_id (header, extracted in middleware), Option C for tenant_id in the short term (reuse `request.project_id` as the tenant surrogate until Forgg establishes a proper tenancy model). Confirm with FORGG as part of go-signal.

**Changes:**

1. `src/api.py` — in both `chat_completion()` and `process_ai_services_compatible()`, after request parsing, attach attributes to the current span:

   ```python
   from opentelemetry import trace
   span = trace.get_current_span()
   span.set_attribute("forgg.tenant_id", project_id)  # from verify_api_key dependency
   conv_id = request.conversation_id or request_headers.get("x-forgg-conversation-id")
   if conv_id:
       span.set_attribute("forgg.conversation_id", conv_id)
   ```

2. Add `conversation_id: str | None` optional field to `ChatCompletionRequest` and `ProcessRequest` as a fallback path (non-breaking — defaults to None).

**Acceptance signal:** A request with `X-Forgg-Conversation-Id: test-123` header produces a SigNoz span with `forgg.conversation_id="test-123"`.

## Step 3 — Instrument the SDK path

**Goal:** Every request that hits `DirectCompletionClient.complete()` produces a wrapping `llm.sdk_path` span with a nested auto-instrumented `gen_ai.*` span for the Anthropic API call.

**Changes:**

1. `src/direct_completion.py` — wrap the body of `complete()`:

   ```python
   from opentelemetry import trace
   tracer = trace.get_tracer(__name__)

   def complete(self, ...):
       with tracer.start_as_current_span("llm.sdk_path") as span:
           span.set_attribute("llm.model", model_id)
           span.set_attribute("llm.max_tokens", max_tokens)
           span.set_attribute("llm.has_tools", tools is not None)
           span.set_attribute("llm.has_system", bool(system_parts))

           # ... existing logic through response = self.client.messages.create(**kwargs) ...
           # OpenLLMetry auto-instruments messages.create → gen_ai.* span nested here

           if has_tool_use:
               span.set_attribute("llm.tool_use_in_response", True)
               span.set_attribute("llm.tool_count",
                                  sum(1 for b in content_blocks if b.get("type") == "tool_use"))

           span.set_attribute("llm.input_tokens", input_tokens)
           span.set_attribute("llm.output_tokens", output_tokens)
           span.set_attribute("llm.cost_usd", cost)
           span.set_attribute("llm.stop_reason", response.stop_reason or "unknown")

           return TaskResult(...)
   ```

2. Error paths (each `except` branch) set `span.set_status(Status(StatusCode.ERROR, ...))` and record the error category. Do NOT put prompt/exception messages on the span — just the category, upstream_status, and a boolean `is_retryable`.

**Critical:** verify OpenLLMetry's `opentelemetry-instrumentation-anthropic` is automatically active after `init_telemetry()`. If not, manually instrument via `AnthropicInstrumentor().instrument()`. FORGG should confirm in Phase 0 library docs.

**Acceptance signal:** A `/v1/chat/completions` request produces a SigNoz trace with three nested spans: HTTP receive → `llm.sdk_path` → `gen_ai.chat.anthropic` (or similar). `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` appear on the nested span.

## Step 4 — Instrument the CLI path + TRACEPARENT injection

**Goal:** The CLI subprocess lifecycle is captured as a span, and the subprocess environment contains a TRACEPARENT pointing back to that span.

**Changes:**

1. `src/worker_pool.py:_start_task_locked()` — wrap the Popen invocation:

   ```python
   from opentelemetry import trace
   from opentelemetry.propagate import inject
   tracer = trace.get_tracer(__name__)

   def _start_task_locked(self, task_id: str):
       # ... existing task setup, temp_dir creation, cmd building ...

       # Build clean environment (existing)
       env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

       # NEW: Inject W3C trace context into subprocess env
       # OTel's propagator writes into a dict-like carrier via a setter.
       inject(env)  # sets TRACEPARENT (and optionally TRACESTATE) in env

       # NEW: Start the subprocess inside a span so the span lifetime
       # matches the Popen lifetime. Span is closed in _process_completed_task
       # via a stashed reference.
       span = tracer.start_span("llm.cli_path.subprocess")
       span.set_attribute("subprocess.model", task.model)
       span.set_attribute("subprocess.timeout_seconds", task.timeout)
       span.set_attribute("subprocess.has_allowed_tools", bool(task.allowed_tools))
       span.set_attribute("subprocess.working_directory", cwd or "<inherit>")
       task.span = span  # stash for completion handler

       try:
           stderr_fh = open(stderr_log, "w")
           task.process = subprocess.Popen(cmd, stdout=..., stderr=stderr_fh,
                                            shell=True, env=env, cwd=cwd, ...)
           span.set_attribute("subprocess.pid", task.process.pid)
           # ... existing status/active_workers bookkeeping ...
       except Exception as e:
           span.set_status(Status(StatusCode.ERROR, str(e)))
           span.end()
           task.span = None
           # ... existing error handling ...
   ```

2. `src/worker_pool.py:_process_completed_task()` — close the span when the subprocess finishes:

   ```python
   def _process_completed_task(self, task_id: str):
       task = self.tasks[task_id]
       # ... existing logic through task.result = TaskResult(...) ...

       if task.span:
           task.span.set_attribute("subprocess.returncode", task.process.returncode or -1)
           if task.status == TaskStatus.COMPLETED:
               task.span.set_attribute("subprocess.input_tokens", input_tokens)
               task.span.set_attribute("subprocess.output_tokens", output_tokens)
           else:
               task.span.set_status(Status(StatusCode.ERROR,
                                            task.result.error_category or "failed"))
           task.span.end()
           task.span = None
   ```

3. Add `span: Any = None` field to the `Task` dataclass.

**Critical — Context propagation across `run_in_executor`:** Every endpoint calls `loop.run_in_executor(None, worker_pool.get_result, task_id, timeout)`. The `get_result` call blocks on a `threading.Event`, not the Popen itself — so the OTel context at the time of `_start_task_locked` is actually correct (it runs inside the main asyncio thread, synchronously before submission returns). BUT: `worker_pool.submit()` is called from the asyncio handler; `_start_task_locked` runs inline (under `self.lock`) in that same asyncio thread IF submit happens via the fast path. If instead the task goes through the queue and `_start_task` runs from `_monitor_loop` (the daemon thread), the span creation happens in a thread with no context.

**Resolution:** Do NOT create the span inside `_start_task_locked`. Instead, create a **parent span in the handler** (before calling `submit`) and pass its context into the Task object:

```python
# In src/api.py _chat_completion_cli (and /v1/process CLI branch):
with tracer.start_as_current_span("llm.cli_path") as parent_span:
    # capture context to pass to worker thread
    parent_ctx = trace.set_span_in_context(parent_span)
    task_id = worker_pool.submit(..., otel_context=parent_ctx)
    result = await loop.run_in_executor(None, worker_pool.get_result, task_id, timeout)
```

Then `_start_task_locked` creates the subprocess span as a child using that context:

```python
with tracer.start_as_current_span("llm.cli_path.subprocess", context=task.otel_context) as span:
    inject(env)  # NOW traceparent reflects the subprocess span, not the handler span
    # ... Popen ...
```

**This is the critical correctness point of the whole effort.** Getting it wrong means CLI-path traces will be disconnected roots. An integration test in step 5 verifies it.

**Acceptance signal:** A `/v1/process` request with `use_cli: true` produces a SigNoz trace with HTTP receive → `llm.cli_path` (handler-level) → `llm.cli_path.subprocess` (monitor-thread-level) spans, and the `TRACEPARENT` env var written into the subprocess matches the `llm.cli_path.subprocess` span ID.

## Step 5 — Integration and regression tests

**Goal:** prevent silent breakage of trace context propagation.

**New test file: `tests/test_trace_propagation.py`**

1. **Test 1: TRACEPARENT reaches subprocess env.** Mock subprocess.Popen to capture `env`. Start a task, verify `env["TRACEPARENT"]` is present and well-formed (W3C 55-byte format).

2. **Test 2: Parent-child span relationship across `run_in_executor`.** Use `opentelemetry.sdk.trace.export.InMemorySpanExporter` to capture emitted spans. Make a /v1/process CLI-path request (mocked subprocess that returns a valid JSON). Verify captured spans include HTTP → `llm.cli_path` → `llm.cli_path.subprocess` with correct parent-child links by trace_id + span_id.

3. **Test 3: SDK path parent-child relationship.** Same pattern, but hit /v1/chat/completions with tools to force SDK path. Verify OpenLLMetry's `gen_ai.*` span is nested inside `llm.sdk_path`.

4. **Test 4: Error spans carry no content.** Trigger a mocked rate_limit error. Verify `span.events[*].attributes` contains no prompt text, only `error_category` and `upstream_status`.

5. **Test 5: contextvars bleed.** Submit 10 concurrent requests with different `X-Forgg-Conversation-Id` values. Verify each trace has the correct conversation_id (i.e., no cross-request contamination through contextvars + ThreadPoolExecutor).

**New test file: `tests/test_latency_budget.py`**

1. **Test 1: p99 SDK path delta.** Run 100 `/v1/chat/completions` requests with OTel disabled, record latency. Run 100 with OTel enabled, record latency. Assert p99 delta < 1%. Use mocked Anthropic responses to eliminate upstream variance.

2. **Test 2: p99 CLI path delta.** Same pattern for `/v1/process` CLI path. Mock Popen to return immediately with a canned JSON response.

Both tests should skip-by-default in CI and run on-demand (marked `@pytest.mark.latency_regression`) to avoid flaky CI signals.

**Acceptance signal:** All five trace propagation tests pass. Both latency tests pass locally. Existing test suite (205 currently passing) shows no regressions.

## Step 6 — End-to-end validation in SigNoz

**Goal:** visually confirm the trace waterfall in SigNoz and rehearse the debugging workflow.

**Prerequisite:** Phase 4a (claude-agents) must be complete so there's an upstream span to connect to. If 4a runs in parallel and isn't done when we finish 4c, we validate against a synthetic caller that sends a `traceparent` header.

**Checklist:**

1. Start a local SigNoz + OTel Collector stack (per FORGG Phase 0 instructions).
2. Start CCAS with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`, `ENVIRONMENT=development`.
3. Make a `/v1/chat/completions` request from either claude-agents (if 4a is done) or `curl` with a synthetic `traceparent` header.
4. Open SigNoz, find the trace, verify:
   - HTTP receive span with correct tenant/conversation attributes
   - Nested `llm.sdk_path` → `gen_ai.chat.anthropic` spans
   - `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.model` populated
   - No prompt/completion text anywhere
   - Structured log lines in the Logs tab correlated by trace_id
5. Make a `/v1/process` request with `use_cli: true`. Verify CLI path spans appear with `subprocess.pid` / `subprocess.returncode`.
6. Trigger a rate-limit error (mock or real). Verify error spans appear with `error_category=rate_limited`, `upstream_status=429`, no content leakage.
7. Write a short "how to debug a CCAS problem using SigNoz" note and link it from `EFFORT.md` for Phase 6 runbook aggregation.

**Acceptance signal:** All six validation steps complete. Runbook snippet drafted.

## Rollout Ordering and Rollback

**Rollout:** This effort ships behind an environment flag, **not** a code flag. If something goes wrong in production, set `OTEL_EXPORTER_OTLP_ENDPOINT=""` and the OTel exporter silently no-ops. No code revert needed for trace export failures.

For the code changes that cannot be env-flagged (middleware, span wrappers), we rely on OTel's "if no exporter, spans are cheap no-ops" guarantee. The latency budget test in step 5 validates this.

**Rollback plan:** If the p99 budget test fails or any existing test regresses, revert the commit. All instrumentation is additive — no existing logic is removed. `src/logging_config.py` is the one exception; preserve the original as `src/logging_config.legacy.py` until Phase 4c is stable in production.

## Effort Estimate

**Best case (everything in `forgg-observability` works as specified):** 3 working days.
- Day 1: Steps 1-2 (wiring + tenant/conversation extraction)
- Day 2: Steps 3-4 (SDK and CLI instrumentation)
- Day 3: Step 5 (tests) + Step 6 (validation) + PR

**Worst case (run_in_executor context helper missing, custom wrapper needed):** 5 working days.
- Extra 1-2 days to write and test the `contextvars.copy_context()` wrapper and route all executor calls through it
- Extra 0.5 day to coordinate fix/patch with FORGG if a library change is needed

**Blocked-on duration:** indefinite until Phase 0 and Phase 3 ship. Based on FORGG timeline, expected start date is approximately 2026-05-02 (3 weeks out).

## Open Questions for FORGG

These are the items waiting on a FORGG response before execution can start. Restated from MSG-CCA-20260411-001 §6 for convenience:

1. **Relaxed subprocess-span exit criterion.** CCAS can only verify `TRACEPARENT` is written into the subprocess env; we cannot verify the Claude Code CLI emits child spans from inside itself (the CLI does not emit OTel). Please confirm this is acceptable.

2. **`run_in_executor` context propagation.** Does `forgg-observability` provide a helper (ideal) or document the pattern (acceptable)? If neither, CCAS will need to write a wrapper and wants FORGG's blessing on the approach.

3. **`allowed_extra_fields` on `setup_logging()`.** CCAS has 10 existing structured-log fields from EFFORT-LLM-Resilience Phase 3 that must survive the library swap. Can `setup_logging()` accept an allowlist extension?

4. **Conversation-ID propagation header convention.** Coordinate with Phase 4a so claude-agents starts sending a consistent header (e.g., `X-Forgg-Conversation-Id`) that CCAS middleware can extract.

## Changelog

- 2026-04-11: Initial draft. Effort created. Awaiting FORGG response to clarifying questions and go-signal to begin execution.
