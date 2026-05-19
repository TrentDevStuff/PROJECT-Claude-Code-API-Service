---
created: 2026-05-19T19:20:00Z
updated: 2026-05-19T19:20:00Z
type: thread
phase: plan
parent_thread: EFFORT-Coordination-Automation/EFFORT.md
child_threads: []
status: draft
wave: 0
backlinks: []
tags: [plan, mesh, phase-1-install, dcaw-mesh-v1]
---

# Plan: DCAW Auto-Agent Mesh Phase 1 Install (v1)

> Spawned by: founder direction 2026-05-19 — "do option (α) on FRG mesh reply (commit to install); update DCAW info; prep for new session to drive install." This plan is authored in the originating session so the next session can review + execute per `INSTALL.md` Flow A.

## Doc Map ^doc-map

```yaml
status: draft
phase: plan
wave-added: 0
addendums: []
last-updated: 2026-05-19T19:20:00Z
target-execution-session: next (TBD; founder-initiated within 1-2 days)
```

### Sections

- [Goal](#^goal)
- [Scope and non-scope](#^scope)
- [Plan structure](#^plan-structure)
- [Phase 1 — Foundation (this EFFORT scaffold)](#^phase-1)
- [Phase 2 — Install execution (next session)](#^phase-2)
- [Phase 3 — Validation + dispatch (next session, after Phase 2)](#^phase-3)
- [Open questions](#^open-questions)
- [Risks](#^risks)
- [Exit criteria](#^exit-criteria)
- [Dependencies](#^dependencies)

## Goal ^goal

Land Phase 1 of the DCAW Auto-Agent Mesh in CCA per `MSG-FRG-20260519-004-to-CCA` recommended scope (home EFFORT only; 0 peers) by 2026-05-21 EOD self-imposed ETA (FRG deadline 2026-05-22 EOD).

## Scope and non-scope ^scope

**In scope (Phase 1):**
- `EFFORT-Coordination-Automation/` as home EFFORT (created this session)
- Mesh protocol file at `.claude/auto-agent-protocol.md`
- launchd plist for INBOX watch (this EFFORT's `INBOX/`)
- on-inbox wrapper script + lifecycle helpers + RUNBOOK
- CCA's Autonomy Charter authored into `EFFORT-Coordination-Automation/EFFORT.md`
- Operating Principles authored to top-level `## Operating Principles` section in `.claude-project/PROJECT.md` (Option A)
- Smoke tests against benign fixtures from `tests/`
- Install-complete dispatch to FRG

**Out of scope (Phase 2+ / future):**
- Peer EFFORTs (0 initially per FRG's right-sizing — `EFFORT-DCAW-Adoption` may join as first peer later when P-3 closes)
- Project-level `~/claude-code-api-service/INBOX/` mesh activation (stays manual per FRG §"Caveats")
- Inter-project bridge (v1.1 follow-on)
- Cross-project dispatch automation (always escalates per `PROTOCOL.md` §7)

## Plan structure ^plan-structure

Three phases, mirroring the mesh package's own ADOPTION-GUIDE structure:

- **Phase 1 — Foundation:** this EFFORT scaffold (done this session)
- **Phase 2 — Install execution:** next session drives `INSTALL.md` Flow A end-to-end
- **Phase 3 — Validation + dispatch:** smoke tests + FRG dispatch + cross-effort updates

## Phase 1 — Foundation (this EFFORT scaffold) ^phase-1

| Item | Status | Notes |
|------|--------|-------|
| **F-1** Create `EFFORT-Coordination-Automation/` folder + subdirs | ✅ done | Per `INSTALL.md` §A.5 `mkdir -p` pattern |
| **F-2** Author DCAW-native `EFFORT.md` (controller w/ Boot Instructions) | ✅ done | Plan-driven EFFORT variant per FRG-002-cc §"Obs (1)" |
| **F-3** Author DCAW-native `plan_mesh-phase1-install.md` (this file) | 🟡 in_progress | ✅ on save |
| **F-4** Dispatch FRG mesh-commit reply | ✅ done | `MSG-CCA-20260519-002-to-FRG` delivered to `~/Forgg/INBOX/` |
| **F-5** Update `EFFORT-DCAW-Adoption` to wave 8 (cross-EFFORT note) | ⏳ pending | Active state + Cross-Project Implications + Wave Log row + frontmatter |
| **F-6** Add `EFFORT-Coordination-Automation` to CCA's `PROJECT.md` Active section | ⏳ pending | Mirror `EFFORT-DCAW-Adoption` entry pattern |
| **F-7** Archive `MSG-FRG-20260519-004-to-CCA` | ⏳ pending | → `INBOX/archive/2026-05-19_MSG-FRG-20260519-004-to-CCA.md` |
| **F-8** Commit + push | ⏳ pending | Single wave-8/wave-0 commit on `feature/phase-4c-instrumentation` OR new branch (founder call) |

## Phase 2 — Install execution (next session) ^phase-2

The substantive install work. Follows `INSTALL.md` Flow A `§A.1 → §A.10` (or whatever the section count is — confirm against package).

### P-1 — §A.1 prereq re-confirmation (next session)

Most prereqs pre-confirmed this session (DCAW rule, Claude CLI, macOS, Opus 4.7). Outstanding for next session:
- `osascript` Notifications permission (System Settings → Notifications)
- launchd registration (verify no FDA permission quirk specific to CCA's plist location)
- Confirm no `EFFORT-Coordination-Automation` placeholder/stale files would break install

### P-2 — §A.2 capture project values (next session)

Locked from this session's reply to FRG (see `EFFORT.md` §"Boot Instructions" Step 4). Don't re-negotiate unless founder explicitly changes scope.

### P-3 — §A.3 install protocol file (next session)

`sed` substitution from `templates/auto-agent-protocol.md.template` → `${PROJECT_ROOT}/.claude/auto-agent-protocol.md`. Verify no `{{...}}` placeholders remain.

### P-4 — §A.4 Operating Principles authoring (next session)

**Option A locked** (top-level `## Operating Principles` section in `PROJECT.md`). Content authoring is where the real thinking happens. Use `templates/coordination-operating-principles.template.md` as scaffold.

**Founder-facing decision points** (consult before writing):
- (OQ-1) Tier-1 routine actions for CCA: auto-ACK FYI cc traffic? auto-archive after triage? auto-confirm receipt?
- Tier-2 escalations: anything from primary recipient? all P-3-related? all `priority: high|critical`?
- Always-escalate floor: cross-project dispatches; user-authored messages; anything modifying running service code

### P-5 — §A.5 scaffold home-EFFORT (next session)

Most of this is **already done this session** (mkdir + EFFORT.md). Remaining:
- Author Autonomy Charter section in EFFORT.md (per `templates/EFFORT.md.charter-section.template`)
- Copy `scripts/on-inbox.sh` → `build/`, chmod +x
- Copy `templates/plist.template` → `build/templates/local.dcaw.watch.plist.template`
- Copy `templates/crontab-line` → `build/templates/dcaw-catchup.crontab`
- Substitute paths via `sed`

### P-6 — §A.6+ lifecycle + RUNBOOK + KNOWN-ISSUES + directory READMEs (next session)

Mechanical copy + substitute steps. Per `INSTALL.md`.

### P-7 — Register launchd plist (next session)

`launchctl bootstrap gui/$UID build/templates/local.dcaw.watch.plist` (substituted path). Verify with `launchctl list | grep dcaw`. **Test fire** by dropping a benign fixture from `tests/` into the watched INBOX; confirm wrapper executes.

### P-8 — Smoke tests (next session)

Per `tests/` README. Validate:
- Wrapper executes on file-event
- Tier-1 routine actions perform correctly (auto-ACK, auto-archive)
- Escalations trigger correctly (osascript notification + escalation file)
- Audit trail accumulates in `confirmations/`
- Daily token ceiling enforced (mock with low ceiling)
- Manual catchup script works (since FRG flagged cron FDA issue)

## Phase 3 — Validation + dispatch (next session, after Phase 2) ^phase-3

| Item | Output |
|------|--------|
| **V-1** All smoke tests green | Log green status in `log_mesh-phase1-install.md` |
| **V-2** Mesh active for real INBOX traffic in `EFFORT-Coordination-Automation/INBOX/` only | (Project-level `~/claude-code-api-service/INBOX/` stays manual) |
| **V-3** Dispatch install-complete to FRG | `MSG-CCA-2026MMDD-NNN-to-FRG` with (a) status, KNOWN-ISSUES hit, installer feedback |
| **V-4** Update `EFFORT-Coordination-Automation/EFFORT.md` | Phase → execute (or completed for install scope); wave 1 row; frontmatter `mesh_status: active` |
| **V-5** Update `EFFORT-DCAW-Adoption` | Cross-Project Implications: note mesh active (potential future peer integration) |
| **V-6** Update `PROJECT.md` | EFFORT-Coordination-Automation status + history note |
| **V-7** Commit + push | Single dispatch-paired commit |

## Open Questions ^open-questions

| OQ | Question | Where to resolve | Lean |
|----|----------|------------------|------|
| OQ-1 | Tier-1 routine actions list specifics (auto-ACK cc'd messages? auto-archive? auto-confirm?) | Operating Principles authoring §A.4 (next session) | Auto-archive after triage; emit confirmation log for routine cc; auto-ACK only for explicit FYI cc with no embedded ask. Anything else escalates. |
| OQ-2 | P-3 verification message routing — escalate or auto-archive? | Operating Principles + Autonomy Charter | Escalate. P-3 is joint-verification consequence; not Tier-1 routine. |
| OQ-3 | Daily token ceiling — keep default 25M or tune to e.g. 5M for CCA's low volume? | Autonomy Charter authoring §A.5 | Keep default 25M; CCA volume naturally low; lower ceiling adds friction for normal operation. |
| OQ-4 | Branch strategy for install commits — continue on `feature/phase-4c-instrumentation` or new branch? | This session F-8 (founder call) | Continue on `feature/phase-4c-instrumentation` for now; the branch is the active coord-work shipping vehicle. Mesh install is doc/scaffold-heavy + new files; clean diff against this branch. |
| OQ-5 | When to add `EFFORT-DCAW-Adoption` as first peer EFFORT? | Future phase (not Phase 1) | After P-3 closes or is formally deferred. Don't add peer EFFORTs until home is operational + smoke-green for at least one calendar week. |

## Risks ^risks

1. **macOS launchd permission quirks.** FRG hit FDA issues with `crontab`; launchd is their primary transport and worked. CCA may hit a different macOS permission (Notifications, Disk Access, etc.) blocking the install. **Mitigation:** `KNOWN-ISSUES.md` review pre-install; user-side System Settings touchpoint confirmed in advance.
2. **Autonomy Charter scope drift.** Writing it well requires careful thought about CCA's coord patterns. Risk: charter is too permissive (mesh ACKs/archives things it shouldn't) or too restrictive (everything escalates → no automation value). **Mitigation:** start conservative (escalate-by-default), then loosen after observing real INBOX patterns over 1-2 weeks.
3. **Side effects on existing CCA work.** Phase 4c instrumentation, running service (PID 35499), open P-3 verification — none should be affected by mesh install (mesh operates on `EFFORT-Coordination-Automation/INBOX/` only). **Mitigation:** confirm scope isolation during P-1 prereq check; abort install if any conflict surfaces.
4. **2026-05-21 ETA slip.** Next session timing depends on founder bandwidth. **Mitigation:** FRG deadline is 2026-05-22 EOD; 1-day buffer. If next session doesn't happen until 2026-05-21, a focused 2-3 hour session can still hit ETA.

## Exit criteria ^exit-criteria

Phase 1 install complete when:

1. ✅ All Phase 2 items (`P-1` through `P-8`) done
2. ✅ All Phase 3 items (`V-1` through `V-7`) done
3. ✅ Smoke tests all green
4. ✅ Mesh active for real INBOX traffic in `EFFORT-Coordination-Automation/INBOX/`
5. ✅ FRG dispatched install-complete; protocol-convention feedback (if any) included
6. ✅ EFFORT-Coordination-Automation phase transitions to `execute` or `completed` depending on whether mesh is considered "operational" (execute) or "install scope done; future Phase 2 work tracked separately" (completed → spawn a new EFFORT for ongoing operations).

## Dependencies ^dependencies

- **Founder availability** for next session (Phase 2 + 3 execution). Self-imposed ETA 2026-05-21 EOD; FRG hard deadline 2026-05-22 EOD.
- **Mesh package at `~/Forgg/EFFORT-DCAW-Mesh-Protocol-Evaluation/dcaw-mesh-package-v1/`** — confirmed present + readable this session.
- **No CCA-side code changes required.** Mesh is fully a scaffold + docs + launchd + bash script install. No Python deps, no service restart.
- **CCA service status irrelevant.** Mesh operates on this EFFORT's INBOX folder, not the running service. Running service can stay up or be stopped without affecting mesh.
