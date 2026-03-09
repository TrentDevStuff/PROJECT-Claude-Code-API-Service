---
type: effort
effort_id: EFFORT-MCP-Tool-Routing
project: PROJECT-Claude-Code-API-Service
status: in_progress
priority: high
progress: 85%
created: 2026-02-16T12:00:00Z
last_updated: 2026-02-16T23:10:00Z
linked_goal: null
---

# EFFORT: MCP Tool Routing

## Overview

Enable agents running through claude-code-api-service to invoke MCP tools (especially advancedmd-mcp on port 8080). This is the critical path for the Feb 24 scheduling demo -- the scheduler agent needs to call MCP tools like `findAppointmentOpenings` and `bookAppointment` through the API service.

## Problem

Currently, claude-code-api-service spawns `claude -p` as a subprocess. The Claude CLI process needs MCP server configuration to access MCP tools. Without it, agents can't reach advancedmd-mcp or any other MCP server.

## Scope

### In Scope

1. **MCP configuration passthrough** -- Ensure spawned Claude CLI processes have access to MCP server config
2. **MCP tool invocation validation** -- Verify agents can actually call MCP tools and get real data back
3. **Permission integration** -- MCP tool access controlled by permission profiles
4. **End-to-end test** -- Agent submits via API -> calls MCP tool -> returns real data

### Out of Scope

- Building new MCP servers
- MCP tool development
- Modifying advancedmd-mcp itself

## Plan

See [[PLAN-2026-02-16-mcp-tool-routing]] for detailed implementation plan.

## Completed Work

### Investigation (Step 1-2) -- 2026-02-16

**Findings:**
- MCP servers stored in `~/.claude.json` (user/local scope) or `.mcp.json` (project scope)
- Claude CLI supports `--mcp-config PATH` flag to pass MCP config to subprocesses
- `CLAUDECODE=1` env var blocks nested CLI sessions — must be stripped from subprocess env
- This project had no `.mcp.json` — spawned `claude -p` subprocesses had no MCP access

**Implementation (Option A+B hybrid):**
1. Created `.mcp.json` in project root with `local-mcp` server at `http://localhost:3001`
2. Added `mcp_config` setting (`CLAUDE_API_MCP_CONFIG` env var) to `src/settings.py`
3. `WorkerPool` accepts `mcp_config` path, appends `--mcp-config` to CLI command
4. Subprocess env strips `CLAUDECODE=1` to allow nested Claude CLI sessions
5. `main.py` passes `settings.mcp_config` to worker pool

**Usage:** Set `CLAUDE_API_MCP_CONFIG=.mcp.json` (or absolute path) to enable MCP routing.

### E2E Testing (Step 3) -- 2026-02-16

**All tests passed with live advancedmd-mcp on port 3001:**

1. **MCP tool discovery:** `/v1/chat/completions` — subprocess listed 122+ MCP tools from `local-mcp`
2. **Patient search:** `/v1/chat/completions` — `searchPatients("Smith")` returned real data (pat6103386 BARB SMITH, pat109085 GREG SMITH)
3. **Scheduling:** `/v1/chat/completions` — `findAppointmentOpenings(Feb 17)` returned real slots (Dr. Joe Black, 7:00/7:15/7:30 AM)
4. **Agentic endpoint:** `/v1/task` with enterprise permissions — full pipeline (permission validation → subprocess → MCP tool → real data), 17s round-trip

**Fix required:** Project-level `.claude/settings.local.json` needed `mcp__local-mcp` in permissions allow list (user-level had it but project-level did not).

### Remaining (Step 4)

- Permission profile integration for MCP tool access (allow/deny specific MCP servers per API key)

## Success Criteria

- [x] Agent submitted via `/v1/task` can call advancedmd-mcp tools
- [x] Real data returned from MCP tool invocation (not simulation)
- [ ] Permission profiles can allow/deny MCP tool access
- [x] End-to-end: API request -> agent -> MCP tool -> real scheduling data

## Related

- Tasks: T-2026-02-03-010, T-2026-02-03-012
- Service: advancedmd-mcp (port 8080, 122 tools)
- Demo: Feb 24 scheduling demo for Tim C.
