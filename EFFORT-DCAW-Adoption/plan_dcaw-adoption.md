---
created: 2026-05-01T20:40:00Z
updated: 2026-05-01T20:40:00Z
type: thread
phase: plan
parent_thread: EFFORT-DCAW-Adoption/EFFORT.md
child_threads: []
status: draft
wave: 1
backlinks: []
tags: [plan, dcaw, attribute-correlation, aca-coord, phase-4c-step-2]
---

# Plan: DCAW Adoption + ACA↔CCA Attribute-Correlation (v1)

> Spawned by: founder ask 2026-05-01 — "create an EFFORT to plan and track the work around the new process that FRG described (DCAW), including Step 4 (4a and 4b)."

## Doc Map ^doc-map

```yaml
status: draft
phase: plan
wave-added: 1
addendums: []
last-updated: 2026-05-01T20:40:00Z
```

### Sections

- [Goal](#^goal)
- [Scope and non-scope](#^scope)
- [Plan structure](#^plan-structure)
- [Phase 1 — Foundation (this EFFORT)](#^phase-1)
- [Phase 2 — First application (Step 4a + 4b)](#^phase-2)
- [Phase 3 — Future applications (placeholder)](#^phase-3)
- [Open questions](#^open-questions)
- [Risks](#^risks)
- [Exit criteria](#^exit-criteria)
- [Dependencies](#^dependencies)

## Goal ^goal

Adopt DCAW T0 conventions in CCA and apply them to the live ACA↔CCA `forgg.cca_request_id` coord — landing the ~10 LOC implementation by ACA's preferred window (~2026-05-02 ideal, 2026-05-04 hard target for Phase 4a Day 7) and demonstrating the cross-project log protocol along the way.

## Scope and non-scope ^scope

**In scope:**
- Authoring this EFFORT's artifacts (EFFORT.md, this plan, the eventual execute log) under DCAW T0 conventions from creation.
- Composing the ACA reply on `forgg.cca_request_id` shape (Step 4a).
- Implementing CCA-side: span attribute + response header (Step 4b).
- Logging inbound/outbound coord traffic as `> [!log]- communication` callouts in the execute log.
- Cross-referencing commits on `feature/phase-4c-instrumentation` from the execute log.

**Not in scope:**
- Retrofitting any existing CCA artifact (T0 only — explicit ask from FRG).
- Generalizing DCAW conventions beyond this EFFORT (other CCA work continues unaffected).
- Code work on Phase 4c Step 3+ (separate Phase 4c roadmap; this plan covers Step 2 only).
- Authoring the `~/Forgg/CLAUDE.md`-equivalent Step-4 boot section in CCA's `CLAUDE.md`. **Deferred unless founder asks.** CCA's auto-loaded global rule already covers protocol mechanics; project-level CLAUDE.md addition is a nice-to-have, not a requirement of T0.

## Plan structure ^plan-structure

Three phases, mirroring DCAW's own phase model. Phase 1 is largely complete just by the act of creating this plan. Phase 2 is the substantive work. Phase 3 is a placeholder for future DCAW applications (we'll know if we need it after Phase 2 lands).

### OQ-3 resolution proposal — single `log_aca-cca-attribute-correlation.md`

The execute log will be **scoped to the first application** (Step 4a + 4b), not to all-future-DCAW-applications. Rationale: keeping the log focused makes the artifact tight and easy to read; if future DCAW work surfaces in CCA, it gets its own thread doc. EFFORT.md remains the durable controller across applications.

## Phase 1 — Foundation (this EFFORT) ^phase-1

| Item | Status | Notes |
|------|--------|-------|
| **F-1** Create `EFFORT-DCAW-Adoption/` folder | ✅ done | 2026-05-01T20:35Z |
| **F-2** Author DCAW-native `EFFORT.md` (controller) | ✅ done | Merged frontmatter, Doc Map, Boot Instructions, Artifact Map, Wave Log |
| **F-3** Author DCAW-native `plan_dcaw-adoption.md` (this file) | 🟡 in_progress | Will be ✅ on save |
| **F-4** Add this EFFORT to project orchestration | ⏳ pending | Update `.claude-project/PROJECT.md` Active section + Forgg coord block. Founder may also want it in `~/.claude/orchestration/projects/`. |
| **F-5** Founder review of plan v1 | ⏳ pending | Plan v1 must be approved before execute kicks off. |

**F-1 → F-3 are essentially complete on save of this file.** F-4 is mechanical bookkeeping. F-5 gates Phase 2.

## Phase 2 — First application: ACA↔CCA attribute correlation ^phase-2

The substantive work. Two sub-items mapping to the user's "Step 4a" and "Step 4b" framing.

### P-1 — Step 4a: Compose ACA coord reply ^p-1

**Inputs:** `INBOX/MSG-ACA-20260430-001-to-CCA.md` (ACA's ask).

**Decisions to make in the reply:**

1. **Header naming (OQ-1 resolution).**
   - Existing CCA infrastructure: `RequestIDMiddleware` already mints `uuid4()` per request, stashes in `scope["state"]["request_id"]`, and echoes `X-Request-Id` response header.
   - **Two viable shapes:**
     - **(A)** Add `X-Forgg-CCA-Request-Id` as a parallel header echo with the same value as `X-Request-Id`. Match `forgg.*` namespace; explicit cross-service contract.
     - **(B)** ACA captures the existing `X-Request-Id` header directly — no new header on CCA side. Smaller footprint; ACA-side ergonomic concern is coupling to a generic header name.
   - **Lean: (A).** Tiny extra cost on CCA side (one line); preserves clean `forgg.*` namespace ACA + FOB asked for. Reuse the same UUID — don't double-mint.
2. **Span attribute scope (OQ-2 resolution).**
   - **Lean: set `forgg.cca_request_id` on every span emitted by Phase 4c instrumentation** (Phase 4c Step 1 already emits the FastAPI HTTP parent span via the OpenLLMetry FastAPI instrumentor + `gen_ai.*` spans on the SDK path / WorkerPool spans on the CLI path). Sourcing: read from `scope["state"]["request_id"]` at the point of span creation. Bake into a small helper if possible to avoid plumbing through call sites.
3. **Echo discipline.**
   - Set the header on every response from `/v1/*` endpoints. `RequestIDMiddleware` already runs on all routes, so adding `X-Forgg-CCA-Request-Id` there is a one-line change next to the existing `X-Request-Id` echo.
4. **Response-body fallback assessment.**
   - ACA's §3.2 fallback (a) — body-embed if header isn't reachable — likely **unnecessary**. The Bun-binary opacity ACA flagged in MSG-ACA-20260429-002 is for *outbound* traceparent propagation from inside the Bun subprocess. Inbound HTTP responses (which is how ACA's Python wrapper sees CCA) are normal HTTP and the wrapper reads them directly. Will note this in the reply but defer to ACA's Day 3-4 verification before locking it down.
5. **Scope estimate.**
   - ACA estimated ~10 LOC. **CCA estimate: ~3-5 LOC** because the request ID infrastructure already exists. Specifically:
     - 1 line in `RequestIDMiddleware.send_with_request_id` to append `X-Forgg-CCA-Request-Id` header.
     - 1-3 lines in span instrumentation (Phase 4c Step 1 init point) to read `request.state.request_id` and set as span attribute. Helper if cleaner.
     - Tests: 2-4 lines per assertion in existing middleware/observability test files.
6. **Timing.**
   - **Confirm 2026-05-02 deliverability.** Realistic given the small scope. Worst case: 2026-05-03; comfortably ahead of ACA's 05-04 hard target.

**Output:** `OUTBOX/MSG-CCA-20260501-002-to-ACA.md` (ack + design confirms + timing). Copied to `~/PROJECT-AI-Claude-Agents/INBOX/`. Logged inline in the execute log as `> [!log]- communication direction=outbox to=ACA`.

### P-2 — Step 4b: Implement CCA-side ^p-2

**Branch:** `feature/phase-4c-instrumentation` (existing — Phase 4c Step 2 ships there).

**Edits (in order):**

1. **`src/middleware.py`**: in `RequestIDMiddleware.send_with_request_id`, append `(b"x-forgg-cca-request-id", request_id.encode("latin-1"))` next to the existing `x-request-id` line. **1 line.**
2. **Phase 4c span attribute helper.** Identify the right hook in the Phase 4c init (likely `forgg-observability`'s span enrichment seam or a small `set_request_id_on_span()` utility called from the FastAPI instrumentor's request hook). Goal: every span in a request's trace carries `forgg.cca_request_id`. **3-5 lines.** May need a 1-line addition to the FOB allowlist call site if v0.3.0 in our pins doesn't include it yet — check on implementation.
3. **Tests (`tests/test_middleware.py` and/or new):**
   - Assert `X-Forgg-CCA-Request-Id` is present on responses with the same value as `X-Request-Id`.
   - Assert it survives across `/v1/chat/completions`, `/v1/process`, `/v1/task`, `/health`. (Use existing test client setup.)
   - If span attribute is testable in-process: assert `forgg.cca_request_id` shows up on a captured span. Otherwise rely on local SigNoz manual verification once both sides land.
4. **Commit.** Conventional commit message:
   `feat(phase-4c): emit forgg.cca_request_id span attr + X-Forgg-CCA-Request-Id response header`
5. **Push** to `feature/phase-4c-instrumentation`.

**Out-of-band coord:** keep ACA in the loop via a brief `> [!log]- plan-execution` callout sequence and one outbound `MSG-CCA-…-to-ACA` "shipped" notification when commits land.

### P-3 — Verify cross-service correlation ^p-3

After ACA's Day 4-5 wires up consumption end-to-end (~2026-05-03 → 05-04):

1. **Joint verification.** Run a coordinated request (CCA serves → ACA wraps) and confirm two trace trees in SigNoz join cleanly via `forgg.cca_request_id` attribute filter.
2. **Document the SigNoz query convention** (one-line reference) in the execute log so future debuggers know the pattern.
3. **Close out.** Final `wave-completion` callout in the execute log; mark plan items closed in this file via inline-pointer + bottom-detail addendum.

## Phase 3 — Future applications (placeholder) ^phase-3

If/when more CCA-side DCAW work surfaces (e.g., Phase 4c Step 3+ has its own coord ask, or another sub-project sends an INBOX message that warrants a thread doc), spawn new `explore_*.md` / `plan_*.md` / `log_*.md` threads inside this EFFORT folder following the same conventions.

**No work for Phase 3 right now.** Mentioning it only so future sessions know this EFFORT is a durable home for DCAW activity, not a one-shot.

## Open Questions ^open-questions

| OQ | Question | Resolution proposal | Status |
|----|----------|---------------------|--------|
| OQ-1 | Header naming — `X-Forgg-CCA-Request-Id` vs reuse `X-Request-Id`? | (A) Add `X-Forgg-CCA-Request-Id` as parallel echo. Cleaner cross-service contract; trivial extra cost. | leaning (A); confirm with founder |
| OQ-2 | Span attribute scope — Phase 4c spans only, or all spans in trace? | All spans emitted by Phase 4c Step 1 init carry the attr. Sourcing: `request.state.request_id`. | leaning broad (all P4c spans); confirm with founder |
| OQ-3 | One log doc for Step 4 only, or one log doc for all-future-DCAW? | Step-4-scoped log; future applications get their own threads. EFFORT.md is the durable controller. | leaning Step-4-scoped; confirm with founder |
| OQ-4 | Update CCA's project `CLAUDE.md` with a DCAW awareness section (mirroring `~/Forgg/CLAUDE.md`'s Step 4)? | Defer unless founder asks. The global rule already covers mechanics. | open — founder call |
| OQ-5 | Register this EFFORT in `~/.claude/orchestration/projects/` per the orchestration system, or keep it CCA-local? | Defer to F-4. CCA already has `~/.claude/orchestration/projects/PROJECT-Claude-Code-API-Service/PROJECT.md`; adding the EFFORT there is mechanical bookkeeping. | open — founder call |

## Risks ^risks

1. **Span instrumentation hook complexity.** If `forgg-observability` v0.3.0 doesn't expose a clean per-span enrichment seam, the "all spans in trace" approach (OQ-2 lean) might require either upgrading to a v0.4.x once it ships or using a custom OpenTelemetry `SpanProcessor`. **Mitigation:** scope-down to "Phase 4c-emitted spans only" if the seam is awkward; ACA's correlation requirement is satisfied either way as long as `agent.execute` parent and the corresponding CCA spans share the attr.
2. **2026-05-02 timing slip.** This is plan + reply + ~5 LOC + tests + commit + push, plus a founder review gate before P-2 starts. If founder approval lands evening of 05-01, P-2 can ship 05-02 morning. If approval slips to 05-02, ship lands 05-02 evening — still ahead of ACA's 05-04 hard target.
3. **Cross-EFFORT artifact discoverability.** Code commits live on `feature/phase-4c-instrumentation` (`EFFORT-Cross-Service-Observability` territory). The execute log here will reference commits by SHA. **Mitigation:** also drop a one-line note in `EFFORT-Cross-Service-Observability/` (probably the existing planning doc) pointing back to this EFFORT for the coord/protocol artifacts. Avoids "where did the design discussion happen" confusion.

## Exit criteria ^exit-criteria

This EFFORT can be marked `completed` when:

1. ✅ ACA reply shipped (P-1).
2. ✅ CCA-side implementation merged on `feature/phase-4c-instrumentation` (P-2).
3. ✅ Joint verification with ACA passes — two trace trees join via `forgg.cca_request_id` in SigNoz (P-3).
4. ✅ FRG ack of T0 adoption acknowledged on FRG side (already in flight via `MSG-CCA-20260501-001-to-FRG`).
5. ✅ Wave-completion callout closes the execute log; this plan's open items all closed via inline-pointer + bottom-detail addendums.

If a Phase 3 application surfaces before exit, EFFORT stays `in_progress` and absorbs it.

## Dependencies ^dependencies

- **Founder approval** of this plan v1 (gates Phase 2 kickoff).
- **ACA-side wiring** lands Day 4-5 of Phase 4a (~2026-05-03 → 05-04). P-3 verification depends on ACA progress.
- **`forgg-observability` v0.3.0** already installed in CCA's environment (per `MSG-CCA-20260413-001-to-FRG` §2). No upgrade required for this scope.
- **No code changes required** for the DCAW adoption itself — the rule auto-loads from `~/.claude-system/rules/`.
