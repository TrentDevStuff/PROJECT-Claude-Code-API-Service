---
created: 2026-05-01T20:35:00Z
updated: 2026-05-01T21:55:00Z
type: effort
project: PROJECT-Claude-Code-API-Service
status: in_progress
priority: medium
owner: trent
current_phase: execute
current_wave: 4
filename_convention: dcaw-native (no-date phase_topic.md)
yaml_convention: merged (per OQ-34 wave-8 close in EFFORT-Document-Centric-AI-Workflow)
dcaw_tier: T0 (forward adoption only — no retrofit)
related_efforts:
  - EFFORT-Cross-Service-Observability  # 4b code work ships on its branch
related_messages:
  - MSG-FRG-20260501-004-to-CCA   # the dispatch (archived)
  - MSG-CCA-20260501-001-to-FRG   # our T0 ack (delivered)
  - MSG-ACA-20260430-001-to-CCA   # the first DCAW application target (archived after reply)
  - MSG-CCA-20260501-002-to-ACA   # design accept reply (delivered + cc'd to FRG)
  - MSG-CCA-20260501-003-to-ACA   # shipped notification, commit ae83653 (delivered + cc'd to FRG)
  - MSG-FRG-20260501-005-cc       # FRG ratification of ACA Wave 3 + §2 ack of CCA direct coord (received cc, archived)
related_commits:
  - ae83653  # feat(phase-4c): emit forgg.cca_request_id span attr + X-Forgg-CCA-Request-Id header [Step 2]
  - d20a3ee  # docs(coord): add EFFORT-DCAW-Adoption + Forgg coord trail for Phase 4c Step 2
  - 9b448eb  # docs(coord): cc-deliveries to Forgg + log MSG-FRG-005-cc receipt
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

**Phase: execute (wave 4, 2026-05-01).** Plan v1 approved-by-action wave 2; first DCAW application (Step 4a + 4b) shipped wave 3; cc-delivery cleanup + FRG MSG-005 triage completed wave 4.

**Active state:**
- P-1 (4a coord reply) ✅ done — MSG-CCA-20260501-002-to-ACA shipped 20:50Z
- P-2 (4b code ship) ✅ done — commit `ae83653` on `feature/phase-4c-instrumentation`, pushed to remote
- P-3 (joint SigNoz verification) ⏳ blocked-on-ACA Day 4-5 (~2026-05-03 → 05-04)
- All cc-deliveries to Forgg ✅ done; loop closed on FRG §2 ask
- `.claude-project/PROJECT.md` registration ✅ done (orchestration symlink target updated)

**Outstanding (deferred per plan):** OQ-4 (CCA `CLAUDE.md` DCAW awareness section), OQ-5 (orchestration registration in `~/.claude/orchestration/projects/`).

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
| 4 | 2026-05-01 | Receipt of FRG MSG-005-cc (Wave 3 ACA ratification with CCA-relevant §2); cc-delivery cleanup; PROJECT.md registration | — | `log_aca-cca-attribute-correlation.md` (FRG inbound + 2 cc-deliveries logged + cc-convention decision); EFFORT.md (frontmatter, current-phase, wave-4 entry); `.claude-project/PROJECT.md` (EFFORT-DCAW-Adoption added to Active) | — | cc-delivery convention codified (`-cc.md` suffix to recipient INBOX). Branch `feature/phase-4c-instrumentation` pushed (3 new commits). |

## Artifact Map ^artifact-map

### Plan phase (closed — approved-by-action wave 2)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| [[plan_dcaw-adoption]] | Plan v1 — DCAW adoption + ACA↔CCA attribute-correlation Step 4a/4b | 1 | approved-by-action |

### Execute phase (active)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| [[log_aca-cca-attribute-correlation]] | Execute log for first DCAW application (Step 4a + 4b) | 2 | open (P-1, P-2 ✅; P-3 blocked-on-ACA) |

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

(Active OQs only; closed/deferred below.)

| OQ | Question | Where | Status |
|----|----------|-------|--------|
| OQ-4 | Add a DCAW awareness section to CCA's `CLAUDE.md` (mirror of `~/Forgg/CLAUDE.md` Step 4)? | [[plan_dcaw-adoption]] §"Open questions" | deferred per plan — founder call |
| OQ-5 | Register this EFFORT in `~/.claude/orchestration/projects/...` per orchestration system? | [[plan_dcaw-adoption]] §"Open questions" | deferred per plan — founder call |

### Closed OQs

| OQ | Status | Outcome |
|----|--------|---------|
| OQ-1 | Closed (wave 2) | Adopted (A): `X-Forgg-CCA-Request-Id` header parallel to existing `X-Request-Id`; same UUID, single mint. Validated by FRG MSG-005-cc §2. |
| OQ-2 | Closed (wave 2) | Adopted broad scope: `forgg.cca_request_id` set on every span emitted during a request via `CCARequestIdSpanProcessor.on_start()` reading from `cca_request_id_ctx` ContextVar. |
| OQ-3 | Closed (wave 2) | Adopted Step-4-scoped log doc; future DCAW applications get their own thread docs. EFFORT.md is the durable controller. |

## Cross-Project Implications ^cross-project

- **ACA**: directly affected — receives the response header / span attribute it asked for. Coord traffic flows through this EFFORT's log.
- **FRG**: lightly affected — observes T0 adoption land cleanly in another project; refines protocol guidance as kickbacks accumulate (none expected).
- **Phase 4c (CCA observability)**: code commits ship there; this EFFORT cross-references commits but doesn't own them.
- **FOB (forgg-observability)**: `forgg.cca_request_id` lands additively in v0.3.x allowlist per ACA-002 §5; no PR needed.

## Next Steps ^next-steps

1. **P-3 verification (blocked-on-ACA).** Joint SigNoz check after ACA Day 4-5 wires up consumption of `X-Forgg-CCA-Request-Id` (~2026-05-03 → 05-04, Phase 4a Day 7). Verify two trace trees (CCA service.name="claude-code-api-service" + ACA service.name="claude-agents") join cleanly via `forgg.cca_request_id` attribute filter.
2. **Sync orchestration repo** (`~/.claude/orchestration`) — `git-sync` to push the `PROJECT.md` change made wave 4 (EFFORT-DCAW-Adoption added to Active section).
3. **Optional — OQ-4 / OQ-5** (founder call):
   - OQ-4: add a DCAW awareness section to CCA's `CLAUDE.md` mirroring `~/Forgg/CLAUDE.md` Step 4.
   - OQ-5: register this EFFORT formally in `~/.claude/orchestration/projects/PROJECT-Claude-Code-API-Service/`.
4. **On P-3 success:** mark this EFFORT `completed`. Optionally keep open as the durable home for future DCAW applications in CCA (per Phase 3 placeholder in plan).
