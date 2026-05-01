---
created: 2026-05-01T20:35:00Z
updated: 2026-05-01T21:05:00Z
type: effort
project: PROJECT-Claude-Code-API-Service
status: in_progress
priority: medium
owner: trent
current_phase: execute
current_wave: 3
filename_convention: dcaw-native (no-date phase_topic.md)
yaml_convention: merged (per OQ-34 wave-8 close in EFFORT-Document-Centric-AI-Workflow)
dcaw_tier: T0 (forward adoption only — no retrofit)
related_efforts:
  - EFFORT-Cross-Service-Observability  # 4b code work ships on its branch
related_messages:
  - MSG-FRG-20260501-004-to-CCA  # the dispatch
  - MSG-CCA-20260501-001-to-FRG  # our ack
  - MSG-ACA-20260430-001-to-CCA  # the first DCAW application target
backlinks: []
tags: [dcaw, forgg-coordination, observability, attribute-correlation, t0-adoption]
---

# EFFORT: DCAW Adoption (Document-Centric AI Workflow)

## Doc Map ^doc-map

CCA's adoption of the Document-Centric AI Workflow protocol per `MSG-FRG-20260501-004-to-CCA` (T0-only forward adoption). First concrete application: the active ACA↔CCA `forgg.cca_request_id` attribute-correlation coord (Step 4a + 4b from session 2026-05-01 triage).

### Sections

- [Boot Instructions for AI](#^boot-instructions)
- [Overview](#^overview)
- [Goal](#^goal)
- [Current Phase](#^current-phase)
- [Phase Transition Log](#^phase-transition-log)
- [Wave Log](#^wave-log)
- [Artifact Map](#^artifact-map)
- [Spawn Tree](#^spawn-tree)
- [Decisions](#^decisions)
- [Open Questions](#^open-questions)
- [Cross-Project Implications](#^cross-project)
- [Next Steps](#^next-steps)

## Boot Instructions for AI ^boot-instructions

**If you are a fresh Claude Code instance pointed at this EFFORT:**

1. **Read this file** — Doc Map → Phase Transition Log → Wave Log → Next Steps. Status is in frontmatter.
2. **Read [[plan_dcaw-adoption]]** for the plan and current execution state.
3. **If execute phase is active:** read [[log_aca-cca-attribute-correlation]] (the live execute log). This is where `plan-execution`, `decision`, `communication`, and `kickback` callouts accumulate.
4. **Source-of-truth references** for protocol mechanics:
   - Auto-loaded rule: `~/.claude-system/rules/document-centric-workflow.md`
   - FRG dispatch: `INBOX/archive/2026-05-01_MSG-FRG-20260501-004-to-CCA.md`
   - Master DCAW EFFORT: `~/Forgg/EFFORT-Document-Centric-AI-Workflow/EFFORT.md`
5. **First-application context** — the live ACA↔CCA coord:
   - ACA ask: `INBOX/MSG-ACA-20260430-001-to-CCA.md`
   - Backstory (why attribute correlation, not traceparent): `INBOX/archive/2026-05-01_MSG-ACA-20260429-002-to-FRG.md`
   - FRG ratification of the contract revision: `INBOX/archive/2026-05-01_MSG-FRG-20260430-001-cc.md`

**T0 scope:** any new artifact created in this EFFORT folder uses DCAW conventions from creation — no-date filenames, merged frontmatter, `> [!log]- type: summary` callouts, `^block-id` anchors, addendum discipline. **No retrofit** of `EFFORT-Cross-Service-Observability/`, `EFFORT-Latency-Optimization/`, or any other existing CCA artifact.

## Overview ^overview

FRG dispatched the DCAW protocol to CCA on 2026-05-01 as a wave-1 onboarding (with FCL, MAP, AIS). CCA was scoped as a **T0-only participant** — forward adoption only, no retrofit. This EFFORT is the first DCAW-native artifact in CCA and serves two purposes:

1. **Vehicle for the protocol adoption itself** — proves the conventions land cleanly in CCA's repo structure and coordination flow.
2. **Container for the first concrete application** — the ACA↔CCA `forgg.cca_request_id` attribute-correlation coord that ACA flagged as the natural first home for the new conventions.

The attribute-correlation work overlaps `EFFORT-Cross-Service-Observability/` (Phase 4c). Code commits ship on the existing `feature/phase-4c-instrumentation` branch as Phase 4c Step 2. **This EFFORT owns the coordination/protocol artifacts; the observability EFFORT owns the code shipping vehicle.** The two are complementary, not competing.

## Goal ^goal

1. Confirm DCAW T0 conventions land cleanly in a CCA-side EFFORT (this one).
2. Close out the ACA↔CCA `forgg.cca_request_id` coord by ACA's preferred window (~2026-05-02 ideal; 2026-05-04 hard target for Phase 4a Day 7 cross-service correlation).
3. Demonstrate the cross-project log protocol (inbound/outbound INBOX traffic logged inline as `> [!log]- communication ...` callouts in the active log thread).
4. Leave a clean, navigable artifact trail for the next CCA AI session and for FRG/ACA cross-references.

## Current Phase ^current-phase

**Phase: plan (wave 1, 2026-05-01).** Plan v1 lives in [[plan_dcaw-adoption]] — DRAFT awaiting founder review. No execute artifact spawned yet.

Once the plan is approved: spawn `log_aca-cca-attribute-correlation.md`, transition `plan -> execute`, and start executing P-1 through P-N from the plan.

## Phase Transition Log ^phase-transition-log

| Date | From | To | Trigger | Notes |
|------|------|----|---------|-------|
| 2026-05-01T20:35Z | (none) | plan | Founder request to create an EFFORT to plan + track DCAW adoption work + Step 4a/4b | Wave 1 began directly in plan phase (skipped explore — protocol mechanics already settled in `~/Forgg/EFFORT-Document-Centric-AI-Workflow/`; this EFFORT is purely an adoption + first-application vehicle). |
| 2026-05-01T20:45Z | plan | execute | Founder direction "plan it first, then implement and track your implementation" — plan v1 approved-by-action; OQ-1/OQ-2/OQ-3 resolved on leans; OQ-4/OQ-5 deferred. | Wave 2 begins. [[log_aca-cca-attribute-correlation]] spawned as first execute artifact. P-1 (4a coord reply) starts immediately. |

## Wave Log ^wave-log

| Wave | Date | Trigger | New artifacts | Subs addended | OQs added | OQs closed |
|------|------|---------|---------------|---------------|-----------|------------|
| 1 | 2026-05-01 | Founder ask: create EFFORT to plan + track DCAW adoption + Step 4a/4b | `EFFORT.md`, `plan_dcaw-adoption.md` | — | OQ-1, OQ-2, OQ-3, OQ-4, OQ-5 (in plan doc) | — |
| 2 | 2026-05-01 | Founder approval-by-action ("plan it first, then implement and track") → phase transition + execute kickoff | `log_aca-cca-attribute-correlation.md` | EFFORT.md (phase transition + wave-2 entry) | — | OQ-1 (lean A), OQ-2 (lean broad), OQ-3 (lean Step-4-scoped); OQ-4 + OQ-5 deferred |
| 3 | 2026-05-01 | Execute work — P-1 (ACA reply) + P-2 (4b code ship) | — | `log_aca-cca-attribute-correlation.md` (plan-execution + decision callouts); EFFORT.md (wave-3 entry) | — | P-1, P-2 closed; P-3 blocked-on-ACA. Implementation decision logged: contextvar + custom SpanProcessor pattern over parent-span-only hook. Commit `ae83653` shipped on `feature/phase-4c-instrumentation`. |

## Artifact Map ^artifact-map

### Plan phase (active)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| [[plan_dcaw-adoption]] | Plan v1 — DCAW adoption + ACA↔CCA attribute-correlation Step 4a/4b | 1 | draft |

### Execute phase (active)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| [[log_aca-cca-attribute-correlation]] | Execute log for first DCAW application (Step 4a + 4b) | 2 | open |

## Spawn Tree ^spawn-tree

```
EFFORT-DCAW-Adoption/
├── EFFORT.md (this file — controller)
├── plan_dcaw-adoption.md (wave 1 — plan v1; approved-by-action wave 2)
└── log_aca-cca-attribute-correlation.md (wave 2 — execute log; active)
```

## Decisions ^decisions

1. **T0-only adoption.** No retrofit of existing CCA artifacts. Confirmed in `MSG-CCA-20260501-001-to-FRG`.
2. **First application = ACA↔CCA `forgg.cca_request_id` coord.** Per FRG dispatch and ACA's open ask. Highest leverage; smallest scope.
3. **Two-EFFORT split.** This EFFORT owns coord/protocol artifacts; `EFFORT-Cross-Service-Observability` owns code commits (continues on `feature/phase-4c-instrumentation` branch as Phase 4c Step 2).
4. **DCAW-native authoring from creation.** All artifacts in this folder use no-date filenames, merged frontmatter, callout log entries, `^block-id` anchors.

## Open Questions ^open-questions

| OQ | Question | Where |
|----|----------|-------|
| OQ-1 | Header naming — accept ACA's `X-Forgg-CCA-Request-Id`, or counter-propose reusing the existing `X-Request-Id`? | [[plan_dcaw-adoption]] §"P-1 4a coord reply" |
| OQ-2 | Span attribute scope — only on `gen_ai.*` spans (Phase 4c spans), or also on the FastAPI HTTP parent span? | [[plan_dcaw-adoption]] §"P-2 4b implementation" |
| OQ-3 | Spawn an explicit `log_*.md` for Step 4 only, or use a single `log_dcaw-adoption.md` for all DCAW applications going forward? | [[plan_dcaw-adoption]] §"Plan structure" |

## Cross-Project Implications ^cross-project

- **ACA**: directly affected — receives the response header / span attribute it asked for. Coord traffic flows through this EFFORT's log.
- **FRG**: lightly affected — observes T0 adoption land cleanly in another project; refines protocol guidance as kickbacks accumulate (none expected).
- **Phase 4c (CCA observability)**: code commits ship there; this EFFORT cross-references commits but doesn't own them.
- **FOB (forgg-observability)**: `forgg.cca_request_id` lands additively in v0.3.x allowlist per ACA-002 §5; no PR needed.

## Next Steps ^next-steps

1. **Founder review of [[plan_dcaw-adoption]]** — approve / push back / refine.
2. **On approval:** transition `plan -> execute`; spawn the execute log; run P-1 (4a coord reply) → P-2 (4b implementation).
3. **On execute completion:** mark this EFFORT `completed` if no further DCAW applications are anticipated, or `in_progress` (idle) if it becomes the durable home for future DCAW applications in CCA.
