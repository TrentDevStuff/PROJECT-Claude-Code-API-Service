# Execution Paths: SDK vs CLI

The Claude Code API Service supports two execution paths for processing requests. Understanding when to use each path is key to optimizing latency and functionality.

## Decision Tree

```
Do you need tools, agents, skills, MCP servers, or working directory context?
├── YES → Use CLI path
│         • /v1/chat/completions (always CLI)
│         • /v1/task (always CLI)
│         • /v1/process with use_cli: true
│
└── NO → Use SDK path (default)
          • /v1/process (SDK by default)
```

## SDK Path (Default)

The SDK path uses the Anthropic Python SDK (`anthropic.Anthropic()`) to call the Anthropic Messages API directly. A persistent client is initialized once at startup and reused for all requests.

**Overhead:** ~50ms + inference time

**What it does:**
- Sends messages directly to the Anthropic Messages API
- Maps provider/model names to Claude models (haiku, sonnet, opus)
- Tracks usage and enforces budgets

**What it cannot do:**
- Use Claude Code tools (Read, Write, Bash, Edit, Grep, Glob)
- Spawn agents or invoke skills
- Connect to MCP servers
- Load CLAUDE.md or project rules
- Access working directory context

**Request example:**
```bash
curl -X POST http://localhost:8006/v1/process \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "model_name": "claude-3-sonnet",
    "user_message": "Explain the difference between TCP and UDP",
    "max_tokens": 500
  }'
```

## CLI Path

The CLI path spawns a `claude -p` subprocess via the worker pool. Each request starts a new Claude CLI process, which initializes the Node.js runtime, loads configuration, and establishes an API connection.

**Overhead:** 3-8s cold start + inference time

**What it enables:**
- Full Claude Code tool access (Read, Write, Bash, etc.)
- Agent spawning and skill invocation
- MCP server connections
- CLAUDE.md and project rules loading
- Working directory context (`working_directory` parameter)
- Allowed tools filtering (`allowed_tools` parameter)

**When to use `use_cli: true` on `/v1/process`:**
- You need Claude to read/write files in a project
- You need MCP tool access (e.g., `mcp__local-mcp__medical_searchPatients`)
- You need project-specific context from CLAUDE.md

**Request example:**
```bash
curl -X POST http://localhost:8006/v1/process \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "model_name": "claude-3-sonnet",
    "user_message": "Read src/api.py and summarize the endpoints",
    "use_cli": true
  }'
```

## Endpoint Summary

| Endpoint | Execution Path | Use Case |
|----------|---------------|----------|
| `POST /v1/process` | SDK by default | Simple completions, multi-provider compatibility |
| `POST /v1/process` + `use_cli: true` | CLI | Completions needing Claude Code features |
| `POST /v1/chat/completions` | CLI always | Chat completions with full Claude Code |
| `POST /v1/task` | CLI always | Agentic multi-step tasks |

## Latency Comparison

| Path | Cold Start | Total (simple prompt) |
|------|-----------|----------------------|
| SDK | None (~50ms overhead) | ~1-3s |
| CLI | 3-8s | ~4-11s |

The SDK path is 3-8x faster for simple completions because it eliminates the CLI subprocess startup entirely.

## Migration from `use_sdk`

Prior to the SDK default change, the field was named `use_sdk` with a default of `false` (CLI was default). If you were using `use_sdk: true`, you can now remove it — SDK is the default. If you need CLI features, add `use_cli: true` to your requests.

| Before | After |
|--------|-------|
| `"use_sdk": true` | Remove (SDK is default) |
| `"use_sdk": false` | `"use_cli": true` |
| No field specified | No change needed (was CLI, now SDK) |
