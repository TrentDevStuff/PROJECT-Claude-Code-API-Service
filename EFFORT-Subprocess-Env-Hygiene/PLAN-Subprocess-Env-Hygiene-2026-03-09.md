---
created: 2026-03-09T12:00:00Z
updated: 2026-03-09T12:00:00Z
type: plan
effort: EFFORT-Subprocess-Env-Hygiene
---

# PLAN: Subprocess Environment Hygiene Fixes

## Context

All LLM calls through the claude-code-api-service fail with HTTP 500 timeout errors when the service inherits `CLAUDECODE` from its parent shell. The root cause is confirmed: subprocess workers inherit the full parent environment, Claude CLI detects the nested session marker and exits immediately, but the error is masked by a 30-second polling timeout.

This plan addresses 4 layers of the problem: the env leak itself, the unused sanitization code, the poor error propagation for fast-failing processes, and the WebSocket error reporting gap.

## Phase 1: Environment Sanitization (Critical — Fixes the Outage)

### Task 1.1: Strip problematic env vars at service startup

**File:** `main.py` (lines 28-60, `lifespan` function)

Add env cleanup before any services are created. This is the broadest fix — strips vars once at process level so all subprocesses inherit a clean env regardless of spawn path.

```python
# At the top of lifespan(), before WorkerPool creation:
import os

# Strip env vars that break Claude CLI subprocesses
_STRIP_ENV_VARS = [
    "CLAUDECODE",           # Prevents nested session detection
    "CLAUDE_CODE_SESSION",  # Future-proofing for similar markers
]
for var in _STRIP_ENV_VARS:
    os.environ.pop(var, None)
```

**Why here:** Single point of cleanup. Even if someone adds a new subprocess path later, it inherits a clean env.

### Task 1.2: Pass sanitized env to worker_pool.py subprocess

**File:** `src/worker_pool.py` (lines 284-293, `_start_task` method)

Defense-in-depth: even if startup cleanup is bypassed, each subprocess gets an explicitly sanitized env. Wire up the existing `SecurityValidator.sanitize_environment()` which is already written but never called.

```python
# In _start_task(), before subprocess.Popen:
import os
from src.security_validator import SecurityValidator

env = os.environ.copy()
env.pop("CLAUDECODE", None)

# Also strip secrets — use the existing sanitizer
validator = SecurityValidator()
env = validator.sanitize_environment(env)

task.process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    text=True,
    executable='/bin/bash',
    env=env,  # <-- ADD
)
```

**Note:** Instantiating `SecurityValidator` per task is cheap (no I/O). Alternatively, create it once in `WorkerPool.__init__` and reuse.

### Task 1.3: Pass sanitized env to websocket.py subprocess

**File:** `src/websocket.py` (lines 356-365, `_stream_response` method)

Same pattern as worker_pool. This is the second subprocess spawn path.

```python
# In _stream_response(), before subprocess.Popen:
import os
from src.security_validator import SecurityValidator

env = os.environ.copy()
env.pop("CLAUDECODE", None)
validator = SecurityValidator()
env = validator.sanitize_environment(env)

process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    text=True,
    bufsize=1,
    env=env,  # <-- ADD
)
```

### Task 1.4: Add CLAUDECODE to SecurityValidator sensitive keys

**File:** `src/security_validator.py` (lines 154-159, `sanitize_environment` method)

Add `CLAUDECODE` and `CLAUDE_CODE_SESSION` to the sensitive keys set so the sanitizer catches them even if the explicit `.pop()` is removed in future refactors.

```python
sensitive_keys = {
    "API_KEY", "SECRET_KEY", "ACCESS_TOKEN", "PASSWORD",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN", "ANTHROPIC_API_KEY",
    "CLAUDECODE", "CLAUDE_CODE_SESSION",  # <-- ADD
}
```

### Task 1.5: Sanitize env in CLI service startup

**File:** `cli/commands/service.py` (lines 139-140)

The CLI `start` command copies `os.environ` and passes it to the service process. Strip problematic vars here too.

```python
env = os.environ.copy()
env["PORT"] = str(service_port)

# Strip vars that break Claude CLI subprocesses
for var in ["CLAUDECODE", "CLAUDE_CODE_SESSION"]:
    env.pop(var, None)
```

---

## Phase 2: Error Propagation (Important — Fixes Misleading Timeouts)

### Task 2.1: Detect immediate process exit in `get_result()`

**File:** `src/worker_pool.py` (lines 155-195, `get_result` method)

The current polling loop in `get_result()` checks `task.result` every 0.1s, but when a process exits immediately, the result isn't set until `_check_completed_tasks` runs on the monitor thread. This means an instant failure still takes up to 30s to surface.

Fix: inside the polling loop, if the process has exited (poll() is not None) but no result is set yet, process the completion inline.

```python
def get_result(self, task_id: str, timeout: float = 30.0) -> TaskResult:
    if task_id not in self.tasks:
        raise ValueError(f"Task {task_id} not found")

    start_time = time.time()
    while time.time() - start_time < timeout:
        task = self.tasks[task_id]

        if task.result:
            return task.result

        # NEW: If process exited but result not yet processed,
        # process it now instead of waiting for monitor thread
        if (task.process and task.process.poll() is not None
                and task.status == TaskStatus.RUNNING):
            self._process_completed_task(task_id)
            if task.result:
                return task.result

        time.sleep(0.1)

    # Timeout handling (unchanged)
    ...
```

**Impact:** Immediate process failures (like the CLAUDECODE error) now return in <0.2s instead of 30s. The error message includes the actual stderr.

### Task 2.2: Include stderr in WebSocket error messages

**File:** `src/websocket.py` (lines 395-401, `_stream_response` method)

Currently when the process exits with non-zero, the error is:
```python
raise RuntimeError(f"Claude CLI exited with code {return_code}")
```

This discards the stderr which contains the actual error message. Fix:

```python
if return_code != 0:
    stderr_output = ""
    try:
        stderr_lines = await asyncio.wait_for(stderr_task, timeout=1.0)
        stderr_output = "".join(stderr_lines).strip()
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    raise RuntimeError(
        f"Claude CLI exited with code {return_code}: {stderr_output}"
    )
```

---

## Phase 3: Service Startup Observability (Recommended)

### Task 3.1: Log service output to file in background mode

**File:** `cli/commands/service.py` (lines 142-151)

Currently background mode sends stdout/stderr to DEVNULL. If the service fails to start (e.g., port conflict, import error), there's zero diagnostic output. Log to a file instead.

```python
if background:
    log_dir = Path.home() / ".claude-api" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "service.log"

    with open(log_file, "a") as log_f:
        process = subprocess.Popen(
            cmd,
            cwd=service_dir,
            env=env,
            stdout=log_f,
            stderr=log_f,
            start_new_session=True
        )

    # ... rest of startup check unchanged
    print_info(f"Logs: {log_file}")
```

### Task 3.2: Add startup self-test

**File:** `main.py` (in `lifespan`, after WorkerPool starts)

Add a lightweight self-test at startup that spawns a single Claude CLI process to verify it can actually run. Catches env issues before the first real request.

```python
# After worker_pool.start():
import subprocess
test_result = subprocess.run(
    ["claude", "-p", "ping", "--model", "haiku", "--output-format", "json"],
    capture_output=True, text=True, timeout=15,
    env=os.environ.copy()  # Already sanitized by Phase 1
)
if test_result.returncode != 0:
    print(f"WARNING: Claude CLI self-test failed: {test_result.stderr}")
else:
    print("✓ Claude CLI self-test passed")
```

**Note:** This adds ~5-10s to startup. Could be made optional via env var `SKIP_SELF_TEST=1`.

---

## Implementation Order

| # | Task | Priority | Risk | Estimated LOC |
|---|------|----------|------|---------------|
| 1.1 | Strip env at startup | Critical | Low | 5 |
| 1.2 | Sanitized env in worker_pool | Critical | Low | 8 |
| 1.3 | Sanitized env in websocket | Critical | Low | 8 |
| 1.4 | Add CLAUDECODE to sanitizer | Critical | None | 2 |
| 1.5 | Sanitize env in CLI start | Critical | Low | 3 |
| 2.1 | Early exit detection in get_result | Important | Low | 6 |
| 2.2 | Stderr in WebSocket errors | Important | Low | 8 |
| 3.1 | Log to file in background mode | Recommended | None | 10 |
| 3.2 | Startup self-test | Recommended | Low | 8 |

**Total estimated change:** ~58 lines across 5 files.

## Testing

### Manual verification (post-Phase 1)

```bash
# 1. Start service from INSIDE a Claude Code session (CLAUDECODE is set)
claude-api service start --background

# 2. Verify health
curl http://localhost:8006/health

# 3. Verify completions work (this was the failing path)
curl -X POST http://localhost:8006/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <key>" \
  -d '{"messages":[{"role":"user","content":"Say hello"}],"model":"haiku","max_tokens":10}'

# Expected: 200 with completion text (was 500 timeout before fix)
```

### Manual verification (post-Phase 2)

```bash
# Temporarily break Claude CLI to test error propagation
# (e.g., rename the binary, or set a bad model name)
# Verify error returns in <2s with actual error message, not 30s timeout
```

### Automated tests to add

- `test_worker_pool_env_sanitization`: Verify CLAUDECODE is not in subprocess env
- `test_worker_pool_fast_fail`: Submit task with bad command, verify error returns in <2s
- `test_websocket_error_includes_stderr`: Verify WebSocket error messages include process stderr

## Risks

- **Phase 1 is zero-risk.** Stripping env vars that shouldn't be there. No behavior change for correctly-started services.
- **Phase 2 has low risk.** `_process_completed_task` is already called from the monitor thread; calling it from `get_result` requires ensuring thread safety (already uses `self.lock`, but `get_result` doesn't currently hold it during the early-exit check — need to acquire lock).
- **Phase 3 self-test adds startup latency.** Make it skippable.

## Dependencies

None. All changes are internal to the service. No schema changes, no API changes, no client library updates.
