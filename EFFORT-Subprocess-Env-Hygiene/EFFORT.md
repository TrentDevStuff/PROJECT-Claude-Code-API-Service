---
created: 2026-03-09T12:00:00Z
updated: 2026-03-09T12:00:00Z
status: not_started
priority: critical
effort_id: EFFORT-Subprocess-Env-Hygiene
project: claude-code-api-service
goal: Fix subprocess environment leakage that blocks all LLM calls
type: effort
dependencies: []
---

# EFFORT: Subprocess Environment Hygiene

## Overview

Fix critical subprocess environment variable leakage in the claude-code-api-service. When the service is started from a Claude Code session (or any shell with `CLAUDECODE` set), all subprocess workers inherit that variable, causing Claude CLI to refuse to start with a "nested session" error. Every `POST /v1/chat/completions` returns HTTP 500 with a generic timeout message, masking the real cause.

This effort also addresses the broader problem: subprocess workers inherit the full parent environment including secrets, and error reporting from immediate process failures is poor.

## Problem Summary

1. **CLAUDECODE env var leaks to subprocesses** — Claude CLI detects it and exits immediately. The service sees a failed process but reports a generic timeout instead of the actual error.
2. **No env sanitization on subprocess spawn** — `SecurityValidator.sanitize_environment()` exists but is never called. Workers inherit API keys, tokens, and credentials from the parent.
3. **Immediate subprocess failures report as timeouts** — When a process exits in <1s, `get_result()` polls for up to 30s before the monitor thread processes the completion, so the caller gets "timed out" instead of the real stderr.
4. **WebSocket streaming path doesn't surface stderr** — `websocket.py` raises `RuntimeError(f"Claude CLI exited with code {return_code}")` without including stderr content.
5. **Background service startup suppresses all output** — `cli/commands/service.py` redirects stdout/stderr to DEVNULL, making startup failures invisible.

## Affected Files

| File | Lines | Issue |
|------|-------|-------|
| `src/worker_pool.py` | 286-293 | No `env` param on Popen; no early-exit detection in `get_result()` |
| `src/websocket.py` | 358-365 | No `env` param on Popen; stderr not included in error messages |
| `main.py` | 28-60 | No env cleanup at startup |
| `src/security_validator.py` | 144-167 | `sanitize_environment()` exists but never called |
| `cli/commands/service.py` | 139-151 | Full env passed without sanitization; output to DEVNULL |

## Success Criteria

- [ ] Service works when started from a Claude Code session
- [ ] Subprocess workers never receive CLAUDECODE, API keys, or credential env vars
- [ ] Immediate process failures return the actual error within 1-2s, not after a 30s timeout
- [ ] WebSocket errors include stderr content
- [ ] Service startup logs to a file when running in background mode

## Investigation Source

See `INVESTIGATION-Claude-CLI-Nested-Session-Block.md` in project root. Discovered during e2e testing of Intelligence Layer Revisions (Phases 1-3).
