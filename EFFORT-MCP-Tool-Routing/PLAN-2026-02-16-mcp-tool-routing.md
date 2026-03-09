---
created: 2026-02-16T12:00:00Z
updated: 2026-02-16T12:00:00Z
type: plan
effort: EFFORT-MCP-Tool-Routing
---

# PLAN: MCP Tool Routing through claude-code-api-service

## Context

The scheduling demo (Feb 24) requires this pipeline:
```
User -> playground chatbot -> claude-code-api-service -> scheduler agent -> advancedmd-mcp -> real scheduling data
```

The gap: claude-code-api-service spawns `claude -p` via subprocess, but the spawned CLI process may not have MCP server configuration.

## Investigation Steps

### Step 1: Understand CLI MCP Config

- How does Claude CLI discover MCP servers? (`.claude/settings.json`, `--mcp` flag, env vars?)
- Does `claude -p` inherit MCP config from the parent environment?
- Test: spawn `claude -p "list available MCP tools"` and see if it finds advancedmd-mcp

### Step 2: Check Worker Pool CLI Invocation

- Read `src/worker_pool.py` to see exactly how `claude -p` is spawned
- What environment, working directory, and flags are passed?
- Can we add MCP server config to the subprocess environment?

### Step 3: Test MCP Access

- Submit a task via `/v1/task` that requires an MCP tool
- Example: "Find available appointment openings for provider PF on Feb 20"
- Verify it reaches advancedmd-mcp and returns real data

### Step 4: Permission Integration

- Ensure MCP tools appear in the permission system
- Add `allowed_mcp_tools` or `allowed_mcp_servers` to permission profiles
- Validate MCP access is gated by API key permissions

## Implementation Options

### Option A: Inherit Parent MCP Config

If the spawned `claude -p` inherits MCP config from `~/.claude/settings.json`:
- No code changes needed
- Just verify it works end-to-end
- Simplest path

### Option B: Explicit MCP Config in Subprocess

If MCP config doesn't inherit:
- Pass MCP server URLs via environment variables to subprocess
- Or pass `--mcp-server` flags to the CLI command
- Requires changes to `worker_pool.py` subprocess invocation

### Option C: API-Level MCP Proxy

If CLI-based MCP doesn't work:
- claude-code-api-service acts as MCP proxy
- Agent makes tool calls -> API intercepts -> calls MCP server directly via HTTP
- Most complex but most controllable

## Recommended Approach

Start with Option A (test if it just works). Fall back to B, then C.

## Timeline

- Step 1-2: 1 hour (investigation)
- Step 3: 1 hour (testing)
- Step 4: 2 hours (if code changes needed)
- Total: 2-4 hours depending on which option is needed
