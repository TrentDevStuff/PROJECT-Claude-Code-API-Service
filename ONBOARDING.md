# ONBOARDING — pick up where we left off

You are a fresh Claude Code instance in `~/claude-code-api-service` (project code **CCA**).
The prior instance finished a productive day on 2026-04-17. This doc is your briefing.

**Do not start executing yet.** Read §1–§4 first, then in §5 think through alternatives before committing to a plan.

---

## 1. TL;DR — what this project is and what you're holding

- **CCA = `claude-code-api-service`** — the LLM routing proxy between the agent runtime (`claude-agents`, port 8005) and Anthropic, running on port **8006**.
- Two request paths share auth / budget / audit / circuit-breakers / error classification:
  - **CLI path** — `WorkerPool` spawns `claude -p` subprocesses. Uses Claude Max subscription. Slow cold start.
  - **SDK path** — `DirectCompletionClient` calls Anthropic Messages API directly. Pay-per-token. Fast. Now prompt-cached.
- Entry point is **`main.py`**, not `src/api.py`. Lifespan wires everything up.
- Participates in the **Forgg inter-AI coordination protocol** — see `~/Forgg/COORDINATION-PROTOCOL.md`. Your code is **CCA**.

---

## 2. What shipped yesterday (2026-04-17) — three commits on `main`

| Commit | One-liner | Why it matters |
|---|---|---|
| `1840e27` | `fix: CircuitBreaker.status() reentrant-lock deadlock` | Root cause of the "every request hangs" symptom that had stalled CCA + blocked PPL-088 Phase 7. Not aiosqlite, not macOS, not uvloop, not Python 3.13 — a reentrant `threading.Lock` acquired twice on the same thread via a `@property` getter inside a `with self._lock:` block. |
| `4da3e92` | `feat: prompt caching on SDK tool-passthrough path` | Two `cache_control` breakpoints on every `DirectCompletionClient.complete()`. Verified live: 99.9% cache-read ratio on warm requests, ~90% input-token cost reduction. Also fixed pre-existing stale dated model IDs (`claude-sonnet-4-6-20250514`, `claude-opus-4-6-20250514`) that were 404-ing every tool-bearing SDK call. |
| `76efd36` | `docs+feat: consolidate /v1/process routing precedence and document architecture` | Made explicit `use_cli=false` honored (prior `or` logic coerced it). Expanded `CLAUDE.md` with the architecture surface Phase 4c will instrument. |

All 309 tests pass. One pre-existing unrelated failure (`test_chat_completion_task_failed` — brittle string-match) documented in `PROJECT.md` for a follow-up tidy.

**Don't re-diagnose the deadlock.** The `aiosqlite` hypothesis in the original `EFFORT-Health-Endpoint-Deadlock` was wrong. That effort is now `completed`. The real fix is in `src/circuit_breaker.py` — extracted `_compute_state_locked()` matching the existing `_start_task_locked` convention in `WorkerPool`.

---

## 3. What FRG said back

I sent `MSG-CCA-20260417-001-to-FRG` summarizing the three commits plus a `WorkerPool._monitor_loop` no-instrument rationale-shift disclosure (original rationale was the aiosqlite/GIL hypothesis that turned out to be wrong — recommended keeping the decision for a different valid reason: 7,200 zero-signal spans/hour/pool).

FRG replied in **`INBOX/MSG-FRG-20260417-005.md`** (currently unprocessed). Clean accept on all three commits. Three concrete asks for Phase 4c PR review, plus one tidy chore, plus one wait-for-trigger item. Read the full message — §4 below is a summary, not a substitute.

### Summary of what FRG wants from CCA going forward

| Where | What | Urgency |
|---|---|---|
| Phase 4c PR (Week 4 Day 2–3, ~2026-04-28) | Use OTel `gen_ai.usage.*` namespace for cache attrs, dotted sub-path form: `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.usage.cache_read.input_tokens`. **Drop `cache_hit_ratio` as a span attribute** — founder prefers letting SigNoz compute from the two counts (avoids derived-metric staleness). | At Phase 4c PR time |
| Phase 4c PR | Cross-check naming alignment with ACA's Contract 4 allowlist (MSG-ACA-20260411-001, archived in `~/Forgg/INBOX/archive/2026-04-11_MSG-ACA-20260411-001-to-FRG.md`). Naming is the same after the corrections above — no conflict, but verify. | At Phase 4c PR time |
| `WorkerPool._monitor_loop` | Stays DO-NOT-INSTRUMENT. Revised rationale: 500 ms cleanup loop × 7,200 spans/hr = no signal value. Revisit only if Phase 4c reveals subprocess-spawn-latency correlations with monitor behavior. | Confirmed |
| `test_chat_completion_task_failed` | Tidy when convenient (brittle string match against a reworded error message; not caused by any recent commit). | Low — when convenient |
| `forgg-observability v0.3.0` | Ships ~2026-04-28 pre-Phase-4 kickoff. Consume when announcement drops. | Wait for trigger |

FRG has no other pending asks on CCA today.

---

## 4. Required reading, in order

**Must-read before taking any action:**

1. **`CLAUDE.md`** (this repo) — architecture, request routing, service graph, CLI subprocess hygiene, asyncio-loop pin rationale. Don't skim — the routing table for `/v1/chat/completions` vs `/v1/process` is non-obvious and you'll want to internalize it.
2. **`INBOX/MSG-FRG-20260417-005.md`** — full FRG response. §2.1 and §2.3 have the attribute-naming guidance in detail; §4 has the WorkerPool rationale table; §5 has the v0.3.0 release scope.
3. **`OUTBOX/MSG-CCA-20260417-001-to-FRG.md`** — what we told FRG. Reading this lets you reconstruct the conversation without guessing.
4. **`~/.claude/orchestration/projects/PROJECT-Claude-Code-API-Service/PROJECT.md`** — orchestration state. Freshly updated yesterday. The **Current Status** paragraph's 2026-04-17 entry is your canonical summary of shipped work. `EFFORT-Cross-Service-Observability` is your next active effort.

**Read if context is needed:**

5. **`~/Forgg/COORDINATION-PROTOCOL.md`** §1 (boot sequence), §2 (message format), §7 (filename conventions). Reference material — revisit only when you need to write a message.
6. **`~/Forgg/COORDINATION-STATE.md`** — cross-project state snapshot. FRG updated it to reflect yesterday's CCA work.
7. **`git log --oneline -10`** — the three new commits plus the surrounding history. `git show 1840e27 4da3e92 76efd36` to see the full diffs.
8. **`src/circuit_breaker.py`**, **`src/direct_completion.py`**, **`tests/test_circuit_breaker.py`**, **`tests/test_direct_completion.py`** — the code that changed yesterday. Small and self-contained. Read before planning any Phase 4c work that touches these modules.

---

## 5. What to do next — **think through the alternatives, don't just execute**

The prior instance proposed three tiers. Before acting, read `INBOX/MSG-FRG-20260417-005.md` in full and then reason about:

### Tier A — immediate, safe, relevant to yesterday's thread (proposed by prior instance, not yet done)

1. **Archive `INBOX/MSG-FRG-20260417-005.md`** per protocol §1.6 (`mv` to `INBOX/archive/2026-04-18_<original-name>.md`). FRG's message is a clean-accept response, no arbiter action needed.
2. **Capture FRG's attribute-naming guidance in `EFFORT-Cross-Service-Observability/`** — a short markdown note covering the corrected attribute names, the "drop ratio, compute in SigNoz" decision, and the ACA naming alignment check. The purpose is to make the Phase 4c Week-4-Day-2 kickoff zero-context-dependent — no re-reading this entire thread.
3. **Tidy `test_chat_completion_task_failed`** — one-line assertion rewrite (string-match against an error message that was long ago reworded). FRG called it "when convenient." Clearing it means future `pytest tests/` runs don't surface a failure that distracts from real regressions.

### Tier B — housekeeping / scope decisions

4. **Decide on `shim_main.py`** (untracked). It's the fallback from when `main.py` was deadlocked. `main.py` is now healthy. Options: (a) delete it — git can always recreate the pattern; (b) move to `docs/examples/` with a "do not deploy" header as a reference for future emergency-shim patterns; (c) leave untracked indefinitely. Prior instance left it untracked pending user direction.
5. **Decide on `.claude-project/daily/2026-04-17_temp.md`** (untracked). Scratch log of prior-instance messages. Not code. Options: delete, or leave — probably just delete.
6. **Consider tightening the anthropic SDK pin** in `pyproject.toml` from `anthropic>=0.25.0` to `anthropic>=0.35,<1.0` to make the OpenLLMetry `0.59.0` compatibility constraint explicit in our own pins (mentioned as a possible Phase 4c prep item in `OUTBOX/MSG-CCA-20260413-001-to-FRG.md` §2). Not a blocker.

### Tier C — wait for trigger

7. **Install `forgg-observability v0.3.0`** when FRG announces the release (~2026-04-28). Re-run import smoke tests; bump pin if needed.

### Tier D — Phase 4c implementation (Week 4 Day 2–3, ~10 days out)

8. `init_telemetry` + `setup_logging` + `ForggLoggingMiddleware` in `main.py` lifespan.
9. Span around `_chat_completion_with_tools` in `src/api.py` using the corrected attribute names from §3. The `DirectCompletionClient._apply_cache_markers()` helper already emits `cache_creation_tokens` / `cache_read_tokens` into the log extras — read those values off the `TaskResult.usage` equivalent and set them on the span.
10. `TRACEPARENT` injection for the CLI path via `run_in_executor_with_context()` (`forgg-observability`'s helper — already installed editable).
11. Skip `WorkerPool._monitor_loop` per FRG §4.

---

## 6. Known loose ends and gotchas

- **Do not re-open `EFFORT-Health-Endpoint-Deadlock`** looking for the aiosqlite fix. The effort is completed; the real bug was elsewhere. `src/budget_manager.py`'s aiosqlite usage remains a theoretical concern but was never the reported bug.
- **`services.yaml` (service-orchestrator)** points at `main.py` — the temporary shim routing is gone. If you need to restart the service, do it through the normal service-orchestrator flow; `main.py` is verified healthy.
- **The `.env` file has `CLAUDE_API_TOOL_PASSTHROUGH_ENABLED=true` and a real `ANTHROPIC_API_KEY`.** Tool-bearing `/v1/chat/completions` requests route to the SDK path. This is required for ACA's tool-calling use case and must stay on.
- **`main.py` strips `CLAUDECODE` and `CLAUDE_CODE_SESSION` env vars on startup.** Don't undo this — it's needed to prevent nested-session deadlocks when the service is launched from inside a Claude Code session. See `INVESTIGATION-Claude-CLI-Nested-Session-Block.md`.
- **`uvicorn` loop is pinned to `asyncio`** (not `uvloop`). Original rationale was a uvloop/GIL hypothesis that turned out to be wrong (the real deadlock was the CircuitBreaker bug). The pin is retained as a conservative default until someone re-runs load tests with uvloop.
- **Pre-existing failing test:** `tests/test_api.py::test_chat_completion_task_failed` — brittle string-match assertion, not caused by recent work. Documented in `PROJECT.md`. Tidy when convenient.
- **Orchestration files live in a separate repo.** `PROJECT.md` is symlinked in from `~/.claude-data/projects/...`. Updates to it don't get committed here — use `git-sync --group meta` when you want to roll meta-repo changes.

---

## 7. Before you start — what "thinking through alternatives" means here

After reading §1–§4 and processing `INBOX/MSG-FRG-20260417-005.md`, don't just execute the prior instance's Tier A list in order. Consider:

- **Is the user asking for something specific this session?** If yes, scope Tier A / Tier B items against that ask — some may not be relevant to the immediate work.
- **Is Tier A still the right batching?** The prior instance recommended doing archive + guidance-capture + test-tidy together as a "3 immediate wins" bundle. But the test tidy is technically unrelated to FRG's reply — it's a standalone chore FRG happened to mention. Consider whether to bundle or separate.
- **Is there a reason to skip capturing the attribute-naming guidance as a document?** The rationale is "zero-context-dependent kickoff." But if Phase 4c starts tomorrow, in-session memory may cover it. If Phase 4c starts in 10 days (current plan), a written note is much safer.
- **Is `shim_main.py` worth keeping as an emergency-shim reference pattern?** Argument for: the pattern is useful and non-obvious. Argument against: we have the full git history and the deadlock bug is now understood; the situation that required the shim shouldn't recur.
- **Does the anthropic SDK pin tightening belong now or during Phase 4c?** Argument for now: smaller scope, reviewable in isolation. Argument for during Phase 4c: keeps the Phase 4c PR self-describing about its dep requirements.

Present your reasoning and a proposed plan to the user before committing to actions. The user's pattern is to prefer brief, specific recommendations with tradeoffs named, not pre-baked execution.

---

**Questions worth asking the user early if anything is unclear:**

- "Do you want Tier A done as a batch now, or scoped to specific items?"
- "Is there a new thread from today I should know about, or are we continuing from yesterday?"
- "Any new inbox messages besides the one FRG sent yesterday?" (always re-scan `INBOX/` at boot per protocol §1.)

Good luck. The codebase is in a clean state — main branch is green, service is healthy, FRG is happy.

— prior instance
