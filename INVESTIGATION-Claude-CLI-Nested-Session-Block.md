---
created: 2026-03-09T00:00:00Z
updated: 2026-03-09T00:00:00Z
type: investigation
priority: critical
---

# INVESTIGATION: Claude CLI Nested Session Block — All LLM Calls Failing

## Problem Statement

Every `POST /v1/chat/completions` request to the claude-code-api-service (port 8006) returns HTTP 500 with `"Task failed: Task timed out after 30.0 seconds"`. The service health check works fine. This has been failing for an unknown duration — possibly since the service was last restarted.

## Root Cause

The worker pool (`src/worker_pool.py`, line ~286) spawns Claude CLI subprocesses:

```python
task.process = subprocess.Popen(
    cmd,  # claude -p "$(cat prompt.txt)" --model haiku --output-format json
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    text=True,
    executable='/bin/bash'
)
```

The subprocess inherits the parent process's environment, which includes the `CLAUDECODE` env var. Claude CLI v2.1.71 detects this variable and refuses to start:

```
Error: Claude Code cannot be launched inside another Claude Code session.
Nested sessions share runtime resources and will crash all active sessions.
To bypass this check, unset the CLAUDECODE environment variable.
```

The subprocess exits immediately with this error, but the worker pool's completion check sees a failed process and the 30-second timeout fires before the error propagates correctly — resulting in a generic timeout error.

## Evidence

1. **Service health check works:** `GET /health` returns `{"status":"ok"}` (no subprocess needed)
2. **All completions fail:** Every `POST /v1/chat/completions` returns 500 (confirmed in `/tmp/service-orchestrator/claude-code-api-service.log` — dozens of consecutive 500s)
3. **Direct CLI test reproduces:** Running `claude -p "Say hello" --model haiku --output-format json` in a shell with `CLAUDECODE` set produces the nested session error
4. **The service was started from a Claude Code session** (or a shell where `CLAUDECODE` was in the environment), so the service process inherited it

## Impact

- **Polyglot Platform IL**: Confidence gate verification, response formatting (natural/schema modes), intent decomposition — all features requiring LLM calls fall back to graceful degradation (raw mode), but are never actually exercised
- **Any other consumer** of the `/v1/chat/completions` endpoint gets 500s

## Required Fixes

### Fix 1: Strip CLAUDECODE from subprocess environment (Critical)

In `src/worker_pool.py`, modify the `subprocess.Popen` call to explicitly remove `CLAUDECODE` from the child environment:

```python
import os

# Build clean env without CLAUDECODE
env = os.environ.copy()
env.pop("CLAUDECODE", None)

task.process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    text=True,
    executable='/bin/bash',
    env=env,  # <-- ADD THIS
)
```

### Fix 2: Capture and surface subprocess stderr (Important)

Currently, when the subprocess fails immediately (like this case), the worker pool waits for the full timeout before returning an error. The stderr output (which contains the actual error message) is never read or surfaced. The error detail should include stderr:

```python
# In _check_completed_tasks or wherever results are processed:
if task.process.returncode != 0:
    stderr_output = task.process.stderr.read()
    task.result = TaskResult(
        task_id=task_id,
        status=TaskStatus.FAILED,
        error=f"Process failed (exit {task.process.returncode}): {stderr_output}"
    )
```

This would have surfaced the nested session error immediately instead of waiting 30 seconds.

### Fix 3: Service startup env hygiene (Recommended)

In `main.py` or wherever the service initializes, strip known problematic env vars at startup so they can't leak to subprocesses regardless of how the service was started:

```python
# At service startup, before creating WorkerPool
import os
os.environ.pop("CLAUDECODE", None)
```

## Verification Steps

After applying fixes:

1. Restart the service: `python3 ~/.claude/skills/service-orchestrator/service_orchestrator.py restart claude-code-api-service`
2. Test: `curl -X POST http://localhost:8006/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer <key>" -d '{"messages":[{"role":"user","content":"Say hello"}],"model":"haiku","max_tokens":10}'`
3. Expected: 200 response with completion text

## Workaround (Immediate)

Restart the service from a clean shell without `CLAUDECODE` set:

```bash
unset CLAUDECODE
python3 ~/.claude/skills/service-orchestrator/service_orchestrator.py restart claude-code-api-service
```

This fixes the running instance but doesn't prevent recurrence.

## Discovered By

Found during e2e testing of Intelligence Layer Revisions (Phases 1-3). All LLM-dependent features (confidence gate, natural/schema formatting, intent decomposition) were falling back to degraded mode because the API service was returning 500s.
