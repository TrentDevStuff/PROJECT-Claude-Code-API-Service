---
created: 2026-05-19T19:15:00Z
updated: 2026-05-19T19:15:00Z
type: effort
project: PROJECT-Claude-Code-API-Service
status: planning
priority: medium
owner: trent
current_phase: plan
current_wave: 0
filename_convention: dcaw-native (no-date phase_topic.md going forward)
yaml_convention: merged
dcaw_tier: T0 (new EFFORT — DCAW-native from creation)
mesh_status: pre-install (Phase 1 home + orchestrator install in flight, dedicated next session)
related_efforts:
  - EFFORT-DCAW-Adoption  # CCA's first DCAW-native artifact; the mesh is an automation layer on top of DCAW v1
related_messages:
  - MSG-FRG-20260519-004-to-CCA  # DCAW Mesh v1 intra-project adoption recommendation (archived)
  - MSG-CCA-20260519-002-to-FRG  # CCA's commit-to-install reply (delivered)
related_commits: []
backlinks: []
tags: [dcaw, mesh, automation, forgg-coordination, phase-1-install, home-effort]
---

# EFFORT: Coordination-Automation (DCAW Auto-Agent Mesh — CCA Phase 1)

## Doc Map ^doc-map

CCA's home EFFORT for the DCAW Auto-Agent Mesh installation per `MSG-FRG-20260519-004-to-CCA`. This folder is the orchestrator + escalation home; the install itself happens in a dedicated next session that boots off the Boot Instructions below.

### Sections

- [Boot Instructions for AI](#^boot-instructions)
- [Overview](#^overview)
- [Goal](#^goal)
- [Current Phase](#^current-phase)
- [Phase Transition Log](#^phase-transition-log)
- [Wave Log](#^wave-log)
- [Artifact Map](#^artifact-map)
- [Spawn Tree](#^spawn-tree)
- [Autonomy Charter (placeholder)](#^autonomy-charter)
- [Open Questions](#^open-questions)
- [Cross-Project Implications](#^cross-project)
- [Next Steps](#^next-steps)

## Boot Instructions for AI ^boot-instructions

**If you are a fresh Claude Code instance pointed at this EFFORT — read this in order:**

### Step 1 — Confirm context

1. You are working in **PROJECT-Claude-Code-API-Service** (CCA).
2. The user wants you to **drive Phase 1 of the DCAW Auto-Agent Mesh installation** per the mesh package's `ADOPTION-GUIDE.md`.
3. **Mesh package location:** `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/`
4. **Scope decided in the prior session (this EFFORT's wave 0 plan):** home EFFORT only (this folder, `EFFORT-Coordination-Automation`); 0 peer EFFORTs initially.

### Step 2 — Read the mesh package (in this exact order)

1. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/README.md` — addressed to YOU (the AI); orient yourself
2. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/ADOPTION-GUIDE.md` — the conversational walkthrough you'll drive with the user
3. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/INSTALL.md` — Flow A specifically (existing DCAW v1 project)
4. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/COMPATIBILITY.md` — prereq verification (most prereqs already confirmed; see "Pre-confirmed" below)
5. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/KNOWN-ISSUES.md` — read in case you hit one
6. `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/templates/coordination-operating-principles.template.md` — for the Operating Principles authoring step

### Step 3 — Read CCA's coord context

1. **This EFFORT.md** (you're here)
2. The plan: `[[plan_mesh-phase1-install]]` (this folder, sibling) — the structured plan for the install, authored in the prior session as a thread doc
3. The trigger message: `INBOX/archive/2026-05-19_MSG-FRG-20260519-004-to-CCA.md`
4. CCA's mesh-commit reply: `OUTBOX/MSG-CCA-20260519-002-to-FRG.md` — what we told FRG; lock in the same scope
5. CCA's canonical T0-from-scratch DCAW example: `../EFFORT-DCAW-Adoption/EFFORT.md` + `log_aca-cca-attribute-correlation.md` (per FRG's recommendation in `MSG-FRG-20260519-004` §"Recommended scope for CCA")

### Step 4 — Pre-confirmed install values

These are locked in from CCA's reply to FRG (`MSG-CCA-20260519-002-to-FRG`). Do not negotiate them with the user unless they explicitly want to change something.

```bash
export PROJECT_NAME="ClaudeCodeAPIService"
export PROJECT_NAME_UPPER="CLAUDECODEAPISERVICE"
export PROJECT_NAME_LOWER="claudecodeapiservice"
export PROJECT_ROOT="/Users/trent/claude-code-api-service"
export PROJECT_HOME="$HOME"
export COORDINATION_EFFORT_NAME="Coordination-Automation"
export COORDINATION_EFFORT_SLUG="coordination-automation"
export COORDINATION_EFFORT_FOLDER="${PROJECT_ROOT}/EFFORT-${COORDINATION_EFFORT_NAME}"
export ORCHESTRATOR_NAME="Orchestration"
export USER_DEADLINES_NOTE="(no current user-stated deadlines)"
```

Project terminal code (for FRG protocol): **CCA**. Don't substitute this into `{{PROJECT_NAME}}` — that's a different concept (full project name vs. terminal code).

### Step 5 — Operating Principles decision

Locked from CCA's reply: **Option A** (add top-level `## Operating Principles` section to `~/claude-code-api-service/.claude-project/PROJECT.md`). The on-inbox wrapper extracts from there.

The actual content of the Operating Principles section is **yours to draft** in coordination with the user. Use `templates/coordination-operating-principles.template.md` as the starting template. CCA-specific principles to consider (founder will refine):
- Tier-1 routine actions: ACK FYI cc messages; archive inbound after triage; emit confirmation logs for routine cc traffic
- Escalation triggers: anything from primary recipient (not just cc); anything with `priority: high|critical`; anything mentioning P-3 verification; anything modifying running service code or `feature/*` branches
- Always-escalate floor: cross-project dispatches; anything authored by user (not from another AI agent)

### Step 6 — Drive the install per ADOPTION-GUIDE.md

Confirm each major step with the user before executing it. **Stop and ask** for any decision the ADOPTION-GUIDE flags as `[ask user]` or requires authoring (e.g., the EFFORT.md Autonomy Charter section, the operating principles content).

When you reach the smoke-test step (`INSTALL.md` §A.6+): use `tests/` fixtures from the mesh package; do NOT test against live CCA INBOX traffic until smoke tests pass.

### Step 7 — On install complete

1. Update this EFFORT.md: phase → execute (if mesh becomes active and starts triaging) or stay in plan if more tweaks expected
2. Add wave-1 row to Wave Log capturing install outcomes + any KNOWN-ISSUES items hit
3. Dispatch follow-up to FRG (`MSG-CCA-2026MMDD-NNN-to-FRG`): (a) installed status, path to this EFFORT, KNOWN-ISSUES hit (or "none"), installer feedback for protocol-convention queue
4. Update `EFFORT-DCAW-Adoption/EFFORT.md` Cross-Project Implications section noting mesh now active
5. Update `~/claude-code-api-service/.claude-project/PROJECT.md` with EFFORT-Coordination-Automation post-install state (status: in_progress or completed depending on what comes next)

### Pre-confirmed prereqs (from prior session)

- ✅ DCAW v1 rule at `~/.claude-system/rules/document-centric-workflow.md`
- ✅ Claude CLI at `/Users/trent/.local/bin/claude`
- ✅ macOS (Darwin)
- ✅ Opus 4.7 high-effort access (Claude Code Max)
- ⏳ macOS Notifications permission for `osascript` — confirm during install
- ⏳ launchd plist registration — confirm during install (FRG hit FDA permission quirk with cron; should not affect launchd)

## Overview ^overview

The DCAW Auto-Agent Mesh v1 is an automation layer on top of DCAW v1 (which CCA already adopted at T0). Where DCAW v1 defines the document substrate (threads, EFFORTs, INBOX/OUTBOX file conventions), the mesh adds **autonomous file-event-driven agents** that:

- Watch project INBOX (and per-EFFORT INBOX) via launchd
- Process inbound messages per a closed Tier-1 allowed-action list
- Auto-ACK routine FYI cc traffic
- Auto-archive after triage
- Escalate anything consequential (primary-recipient dispatches, high/critical priority, blockers, anything outside the Tier-1 list)
- Maintain an audit trail of routine peer-to-peer coordination

CCA's expected inbound mesh-event volume is **low** (~1-3 messages/wave during active dispatch cycles, idle weeks otherwise). The mesh's value at CCA is primarily:
1. Unattended triage between founder sessions (CCA has 1-2 week response gaps for non-urgent traffic)
2. Audit trail of routine cc messages (avoids re-reading FYI traffic at session boot)
3. Cohort participation in the mesh dispatch wave (alongside FCL, MAP, FRG)

## Goal ^goal

1. Install Phase 1 of the DCAW Auto-Agent Mesh in CCA per FRG's recommended scope (home EFFORT only; 0 peers).
2. Author CCA-specific Autonomy Charter + Operating Principles capturing CCA's coord patterns.
3. Pass mesh smoke tests against benign fixtures (no live INBOX triage until smoke green).
4. Report install outcome + any KNOWN-ISSUES hit + installer feedback to FRG.
5. Stay within FRG's deadline (2026-05-22 EOD) — currently committed to 2026-05-21 EOD self-imposed.

## Current Phase ^current-phase

**Phase: plan (wave 0, 2026-05-19).** Plan authored same wave as EFFORT creation. **Execute phase opens when the next Claude Code session boots and drives `INSTALL.md` Flow A per the Boot Instructions above.**

## Phase Transition Log ^phase-transition-log

| Date | From | To | Trigger | Notes |
|------|------|----|---------|-------|
| 2026-05-19T19:15Z | (none) | plan | Founder direction to scaffold this EFFORT so a dedicated next session can drive the install cleanly off Boot Instructions | Wave 0 — EFFORT.md + plan thread doc authored in same session as FRG-004 receipt + reply; install execution deferred to next session per founder preference for clean context window. |

## Wave Log ^wave-log

| Wave | Date | Trigger | New artifacts | Subs addended | OQs added | OQs closed |
|------|------|---------|---------------|---------------|-----------|------------|
| 0 | 2026-05-19 | EFFORT creation in response to MSG-FRG-20260519-004-to-CCA + founder direction to prep for dedicated install session | `EFFORT.md`, `plan_mesh-phase1-install.md` | — | OQ-1, OQ-2, OQ-3 (in plan doc) | — |

Per FRG's `MSG-FRG-20260505-002-cc` codification: this is a **plan-driven EFFORT** (not thread-doc/explore-driven). `current_wave: 0` baseline; future waves recorded only on cross-project coordination shifts (not on routine install steps).

## Artifact Map ^artifact-map

### Plan phase (active)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| `[[plan_mesh-phase1-install]]` | Plan v1 — DCAW Mesh Phase 1 install (home + orchestrator) | 0 | draft (next session reviews + drives execution) |

### Execute phase (pending)

| Document | Topic | Wave | Status |
|----------|-------|------|--------|
| TBD | Install execution log (likely `log_mesh-phase1-install.md`) | 1 (next session) | not_yet_authored |

## Spawn Tree ^spawn-tree

```
EFFORT-Coordination-Automation/
├── EFFORT.md (this file — controller)
├── plan_mesh-phase1-install.md (wave 0 — plan v1; awaits next-session review + execute)
├── INBOX/ (mesh-managed; empty)
│   └── archive/ (empty)
├── OUTBOX/ (mesh-managed; empty)
│   └── archive/ (empty)
├── escalations/ (mesh-managed; empty)
│   └── archive/ (empty)
├── confirmations/ (mesh-managed; empty)
└── build/ (install artifacts go here)
    └── templates/ (plist + crontab; populated during install)
```

## Autonomy Charter ^autonomy-charter

**[PLACEHOLDER — to be authored during install per `templates/EFFORT.md.charter-section.template`]**

This section will be filled in by the next session during install per `INSTALL.md` §A.5. It defines:
- What the mesh's auto-agents may do autonomously on CCA's behalf (Tier 1)
- What requires escalation (everything else)
- Always-escalate floor (founder-defined)
- Daily token ceiling (default 25M; may tune for CCA's low-volume profile)
- Always-archive-after-triage policy (default true)

**Until this section is authored, the mesh is NOT active.** Even if the plist is registered and the wrapper script is on disk, the mesh requires this charter to be present + non-placeholder before the on-inbox wrapper will execute any Tier-1 action.

## Open Questions ^open-questions

| OQ | Question | Where | Status |
|----|----------|-------|--------|
| OQ-1 | Tier-1 allowed-action list specifics for CCA — should we auto-ACK cc'd MSG-FRG-*-cc.md traffic or just auto-archive after triage? | [[plan_mesh-phase1-install]] | open — next session decides with founder |
| OQ-2 | Escalation trigger for P-3 verification — when ACA finally replies, should mesh auto-archive (it's a P-3 status update) or auto-escalate (it's joint-verification-relevant)? | [[plan_mesh-phase1-install]] | open — likely escalate (joint verification is consequential) |
| OQ-3 | Daily token ceiling tune — default is 25M; CCA's expected volume is ~1-3 events/wave; tune to lower ceiling (e.g., 5M) as additional safety, or keep default? | [[plan_mesh-phase1-install]] | open — likely keep default; CCA volume is naturally below ceiling |

## Cross-Project Implications ^cross-project

- **FRG**: directly affected — receives install-outcome dispatch + any KNOWN-ISSUES feedback; participates in protocol-convention candidate queue updates if installer-shape issues surface.
- **ACA, MAP, FCL, AGO, FOB, AIS, SSD, PPL** (all DCAW participants): indirectly affected — mesh's auto-ACK of cc traffic from these peers reduces founder bandwidth load; no protocol change required on their side.
- **EFFORT-DCAW-Adoption** (sibling EFFORT): the canonical T0-from-scratch example per FRG's recommendation. Mesh install does not modify it; once install complete, mesh may eventually auto-triage `EFFORT-DCAW-Adoption/INBOX/` traffic (currently empty; reserved for future P-3 follow-on coord).

## Next Steps ^next-steps

**This session (2026-05-19):** done after EFFORT scaffold + plan thread doc + FRG/ACA dispatches + DCAW-Adoption wave-8 update + PROJECT.md update + commit + push. No execute work this session.

**Next session (TBD; founder-initiated within 1-2 days for 2026-05-21 EOD ETA):**

1. Boot off the Boot Instructions in §"Boot Instructions for AI" above
2. Read mesh package per Step 2
3. Drive Phase 1 install per `INSTALL.md` Flow A
4. Author Autonomy Charter + Operating Principles with founder
5. Pass smoke tests against `tests/` fixtures
6. Dispatch install-complete notification to FRG
7. Update this EFFORT (wave 1) + EFFORT-DCAW-Adoption (Cross-Project Implications) + PROJECT.md

**Out of scope this EFFORT:** peer EFFORT additions; project-level INBOX/ mesh activation (stays manual per Phase 1); inter-project bridge (v1.1 follow-on).
