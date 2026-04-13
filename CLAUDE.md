# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Inter-Project Coordination (Forgg Protocol)

This project participates in the Forgg inter-AI coordination protocol as **CCA** (claude-code-api-service). It was onboarded on 2026-04-10 for `EFFORT-Cross-Service-Observability` (FORGG Cycle 4).

**On session start, before other work:**
1. Read own state/backlog (README.md, active EFFORTs)
2. Read own architecture docs
3. Read `~/Forgg/EFFORT-Forgg-Jarvis-Architecture/ARCHITECTURE.md` (for Cycle 4 onwards)
4. Process all files in `INBOX/` — validate, create EFFORTs or respond, archive
5. Report inbox summary + prioritized next steps to user

**To communicate with another project:**
1. Create message in `OUTBOX/` following `~/Forgg/COORDINATION-PROTOCOL.md` format (see §7.1 for filename convention: `MSG-CCA-{YYYYMMDD}-{seq}-to-{recipient-code}.md`)
2. `cp` it to the target project's `INBOX/`

**To escalate:** Create `type: escalation` in `OUTBOX/`, `cp` to `~/Forgg/INBOX/`

**Full protocol:** `~/Forgg/COORDINATION-PROTOCOL.md`
**Current state:** `~/Forgg/COORDINATION-STATE.md`

**Project codes reference:** FRG (FORGG arbiter), PPL, FCL, AGO, SSD, MAP, ACA (AI Claude Agents), AIS (AI Service), **CCA (this project)**

## Project Role

claude-code-api-service is the LLM routing proxy between the agent runtime (claude-agents, port 8005) and LLM providers. Runs on port 8006. Provides two endpoints:
- `/v1/process` — SDK agent dispatch (proxy to Claude Agent SDK subprocess)
- `/v1/chat/completions` — OpenAI-format chat completions (IL CLI agents)

Both endpoints support tool calling when `TOOL_PASSTHROUGH_ENABLED=true`. Bearer token authentication required.
