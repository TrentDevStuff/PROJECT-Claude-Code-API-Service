---
created: 2026-04-18T00:00:00Z
updated: 2026-04-18T00:00:00Z
type: note
effort: EFFORT-Cross-Service-Observability
status: guidance-captured
source_messages:
  - MSG-FRG-20260417-005 (§2.1, §2.3 — FRG attribute naming response)
  - MSG-FRG-20260417-008 (§CCA — v0.3.0 release confirmation re: attrs)
  - MSG-ACA-20260411-001 (archived in ~/Forgg/INBOX/archive/) — ACA Contract 4 allowlist reference
---

# Phase 4c Attribute-Naming Guidance

Captured 2026-04-18 while processing MSG-FRG-20260417-005 and -008.
Purpose: make the Week-4-Day-2 Phase 4c kickoff (~2026-04-28) zero-context-dependent.

## Original CCA proposal (MSG-CCA-20260417-001 §5)

Expose two first-class span attributes when Phase 4c SDK spans go live:

- `gen_ai.cache_read_tokens`
- `gen_ai.cache_hit_ratio`

Rationale: cache-hit ratio is a first-class cost/latency signal that belongs on the LLM span. Default-on; drop if span-attribute budget becomes tight.

## FRG response (MSG-FRG-20260417-005 §2)

**Accepted in principle.** Final disposition at Phase 4c PR review.

Three conditions for final acceptance:

### 1. Use `gen_ai.usage.*` namespace with dotted sub-path form

Not `gen_ai.cache_read_tokens`. Use:

- `gen_ai.usage.cache_creation.input_tokens`
- `gen_ai.usage.cache_read.input_tokens`

This is OTel GenAI semantic-convention compliant and matches AIS's existing usage. Also matches ACA's Contract 4 addendum request (MSG-ACA-20260411-001).

### 2. Drop `cache_hit_ratio` as a span attribute

Founder prefers letting SigNoz compute the ratio from the two count attributes. Rationale: avoids derived-metric staleness when backfilling / replaying spans.

We still **log** `cache_hit_ratio` in every `sdk_direct_completion` record (that exists today in `DirectCompletionClient._apply_cache_markers()`) — that's unaffected. The guidance applies only to the span-attribute set.

### 3. Opt-in if cardinality pressure appears

Default-on is fine for now. Revisit if span-attribute budget gets tight.

## ACA Contract 4 allowlist alignment

ACA's MSG-ACA-20260411-001 requested three bonus attributes:

- `gen_ai.usage.cache_creation.input_tokens`
- `gen_ai.usage.cache_read.input_tokens`
- `gen_ai.usage.total_tokens`

Our corrected names (above) match the first two exactly. Check `ALLOWED_SPAN_ATTRIBUTES` in `forgg-observability/.../constants.py` before PR submission to confirm no drift.

Referenced message archived at:
`~/Forgg/INBOX/archive/2026-04-11_MSG-ACA-20260411-001-to-FRG.md`

## Implementation hook points

Read these from the `TaskResult.usage` equivalent returned by `DirectCompletionClient.complete()` and set them on the SDK span in `src/api.py::_chat_completion_with_tools`:

- `cache_creation_tokens` — already present in log extras via `_apply_cache_markers()`
- `cache_read_tokens` — already present in log extras

Source values already captured; attribute naming is the only thing Phase 4c needs to get right.

## Not covered by this note (out of scope)

- CLI-path cache attributes — cache markers only apply on the SDK path; CLI spans won't carry them.
- Tool-use / no-tool-use distinction — `CLAUDE_API_PROMPT_CACHING_ENABLED` controls cache markers; when off, neither token count should be emitted as span attrs.
- `WorkerPool._monitor_loop` instrumentation — DO-NOT-INSTRUMENT per FRG §4 (500ms × 7200 zero-signal spans/hr). Revisit only if subprocess-spawn-latency correlations with monitor behavior appear.

## forgg-observability v0.3.0 — install status (2026-04-18)

- Library exists at `/Users/trent/PROJECT-Forgg-Observability` (v0.3.0 tagged on local main at `b624e35`).
- **Not currently installed in CCA venv** (`/Users/trent/claude-code-api-service/venv`). Phase 4c Step 1 adds `forgg-observability[fastapi,redis,llm]` to `requirements.txt`, so this is anticipated — not a blocker.
- When Phase 4c starts, run `forgg-observability check` in CCA venv after editable install to confirm instrumentors resolve cleanly (per MSG-FRG-20260417-008 §CCA).
