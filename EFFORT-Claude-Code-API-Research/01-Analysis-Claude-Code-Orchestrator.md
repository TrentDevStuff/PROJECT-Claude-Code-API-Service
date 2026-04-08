---
created: 2026-01-30T13:40:00Z
updated: 2026-01-30T13:40:00Z
type: analysis
---

# Analysis: Claude Code Orchestrator - How It Uses Claude Code CLI

This document analyzes how the claude-code-orchestrator project (by cyberkrunk69) leverages Claude Code CLI for multi-agent autonomous development workflows.

## Executive Summary

The orchestrator uses Claude Code CLI as its core LLM engine through direct command-line invocation with carefully designed patterns to:
- Spawn multiple parallel AI workers in terminal tabs
- Track token usage via JSON output format
- Route work to different models (Haiku/Sonnet/Opus) for cost optimization
- Coordinate via filesystem (no servers/ports needed)
- Achieve 60-70% cost savings vs. single-session Claude usage

## Core Mechanism

### 1. Orchestrator Session

**Launch Command** (from `claude-orch.sh` line 182-184):
```bash
claude --system-prompt "$(cat .claude/master-prompt.md)" --model sonnet
```

**What it does:**
- Loads 42KB system prompt from file
- Launches interactive Claude Code session
- User interacts with planning/monitoring orchestrator
- Orchestrator NEVER reads code directly (spawns helpers instead)

### 2. Worker Sessions

**Spawn Command** (from `worker-daemon.py` line 271-275):
```bash
# Read prompt into variable (preserves TTY)
prompt=$(cat 'worker-block.txt')

# Pass as argument to Claude
claude -p "$prompt" --model haiku --dangerously-skip-permissions --output-format json
```

**Key flags:**
- `-p "$prompt"` - Pass prompt as CLI argument (short for `--system-prompt`)
- `--model haiku|sonnet|opus` - Select model for cost/capability trade-off
- `--dangerously-skip-permissions` - Full automation mode (no approval prompts)
- `--output-format json` - Capture token usage data

**Why read-then-pass instead of piping:**
- Piping destroys TTY (breaks interactive mode)
- Reading into variable preserves stdin as TTY
- Shell properly quotes the variable content

### 3. Token Usage Tracking

**Output Format** (worker stdout):
```json
{
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_read_input_tokens": 890,
    "cache_creation_input_tokens": 234
  },
  "total_cost_usd": 0.012
}
```

**Daemon parses this every 30s** (from `worker-daemon.py` lines 692-761):
- Reads `workspace/session_output.json`
- Extracts token counts
- Updates `initiatives.json` with actual usage
- Raises budget alerts when limits exceeded

## Architecture Components

### Worker Daemon (`worker-daemon.py`)

**Purpose:** Background process that watches for work and spawns terminal sessions

**Key Responsibilities:**
1. Watch `.claude/pending_workers/` for manifest files
2. Generate platform-specific launch scripts (PowerShell/Bash)
3. Spawn workers in terminal tabs (Windows Terminal, Terminal.app, gnome-terminal)
4. Monitor token usage and update tracking
5. Auto-close workers when initiatives complete
6. Respawn crashed workers (continuation mode)

**Platform Detection:**
```python
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
```

**Terminal Spawning:**
- **Windows**: `wt new-tab` (Windows Terminal multi-tab)
- **macOS**: `osascript` to open tabs in Terminal.app
- **Linux**: `gnome-terminal --tab` or fallback to xterm

### Launcher Script (`claude-orch.sh`)

**Purpose:** Entry point for starting the orchestrator

**Workflow:**
1. Pre-flight checks (Python, Claude CLI installed)
2. Install watchdog dependency if needed
3. Model selection menu (haiku/sonnet/opus)
4. Permission mode selection (bypass/respect)
5. Clean up stale daemon processes
6. Start fresh daemon in background
7. Launch orchestrator session with system prompt

**Daemon Cleanup** (lines 105-137):
```bash
# Kill by PID from previous run
if [ -f ".claude/.daemon-pid" ]; then
    OLD_PID=$(cat ".claude/.daemon-pid" 2>/dev/null)
    kill -9 "$OLD_PID" 2>/dev/null
fi

# Find and kill any remaining worker-daemon.py processes
STALE_PIDS=$(pgrep -f "worker-daemon.py" 2>/dev/null)
echo "$STALE_PIDS" | while read pid; do
    kill -9 "$pid" 2>/dev/null
done
```

### Launch Helper (`launch-orch.py`)

**Purpose:** Bypass Windows cmd.exe 8192 character limit for long prompts

**Problem:** System prompts can be 31KB+ but cmd.exe has ~8KB argument limit

**Solution:**
```python
with open("master-prompt.md", "r", encoding="utf-8") as f:
    system_prompt = f.read()

args = ["claude", "--system-prompt", system_prompt]
subprocess.call(args)  # Bypasses shell limit
```

## Filesystem-Based Coordination

**No servers, no ports, no auth** - all coordination via files:

### `initiatives.json`
Master state file tracking all work:
```json
{
  "initiatives": [
    {
      "id": "INIT-XXX",
      "title": "Feature description",
      "status": "in_progress",
      "token_budget": 15000,
      "tokens_used": 8500,
      "branch": "feature/INIT-XXX-desc",
      "workspace": ".claude/workspaces/INIT-XXX",
      "progress_log": ["phase_1_complete: ...", "..."]
    }
  ]
}
```

### `pending_workers/`
Drop folder for worker spawn requests:
```
pending_workers/
├── manifest.json          # Triggers daemon (write this LAST)
└── INIT-XXX_worker.txt    # Worker prompt (write this FIRST)
```

**manifest.json:**
```json
{
  "initiative_id": "INIT-XXX",
  "workers": [
    {"file": "INIT-XXX_main.txt", "model": "sonnet", "type": "main"},
    {"file": "INIT-XXX_helper.txt", "model": "haiku", "type": "helper"}
  ]
}
```

**Critical ordering:**
1. Write worker block files FIRST
2. Write manifest.json LAST (triggers daemon)
3. Daemon detects manifest, spawns workers, deletes files

### `workspaces/INIT-XXX/`
Per-initiative work directories:
```
workspaces/INIT-XXX/
├── instructions.txt       # Main → Helper task queue
├── findings.txt           # Shared discoveries
├── results/               # Helper output
├── session_output.json    # Token usage data
├── logs/                  # Worker session logs
└── pids/                  # Process IDs for auto-close
```

## Cost Optimization Strategy

### Model Routing (8x Savings)

**Cost multipliers** (from HAIKU_EFFICIENCY_COMMITMENT.md):
- Haiku: 1x baseline
- Sonnet: 3.75x more expensive than Haiku
- Opus: 18.75x more expensive than Haiku

**Delegation pattern:**
- Orchestrator (Opus): Planning, complex reasoning only
- Main workers (Sonnet): Implementation, coordination
- Helper workers (Haiku): Exploration, batch ops, simple tasks

**Example savings:**
```
Main worker reads 5 files to understand context:
  Sonnet cost: 8,000 tokens × $0.003/1K = $0.024

Main worker spawns Haiku helper to analyze and report:
  Helper delegation: 200 tokens (instruction)
  Helper execution: 1,500 tokens (analysis)
  Main reads summary: 500 tokens
  Total: 2,200 tokens × $0.0004/1K = $0.0009

Savings: $0.024 - $0.0009 = $0.0231 (96% cheaper!)
```

### ORCH-001 Efficiency Protocol

**Core rule:** NEVER use inline agents (Task tool), ALWAYS spawn terminal workers

**Why:**
- Inline agents block the expensive session
- No efficiency prompts (lack ORCH-001 discipline)
- Results dump into expensive context
- No budget tracking or circuit breakers

**Instead:** Spawn cheap terminal helpers via daemon
- Non-blocking (orchestrator keeps working)
- Helper runs with zero-think protocol
- Minimal token usage (execute exactly, no exploration)
- Budget tracked independently

### Token Budget Zones

| Zone | Budget Used | Worker Behavior |
|------|-------------|-----------------|
| GREEN | 0-50% | Normal operations |
| YELLOW | 50-75% | Delegate everything, no optional work |
| RED | 75-90% | Emergency mode, max delegation |
| HALT | 90-100% | STOP, write status, set "blocked_budget" |

**Circuit breaker:** Workers self-halt at 90% budget to prevent runaway costs

## Git Safety & Branching

**Core principle:** Main branch stays stable, features on branches, test before merge

### Branch Lifecycle

```
Initiative created
  → git checkout -b feature/INIT-XXX-description
  ↓
Workers build on feature branch
  → Checkpoint commits as they go
  ↓
Workers complete
  → Run test suite on feature branch
  ↓
Tests pass?
  ├─ YES → git merge feature/INIT-XXX --no-ff (preserve history)
  │        → Mark initiative "done"
  └─ NO  → Worker retries fix (up to 2 attempts)
           → Still failing?
              → git checkout main (abandon branch)
              → Mark initiative "failed_rolled_back"
              → Log failure, move on
```

**Safety guarantees:**
- Main never touched directly by workers
- Every feature isolated on branch
- Full rollback on test failure
- Checkpoint commits = full trail

## Swarm Mode (Complex Tasks)

**When to use:** 50+ atomic changes, parallelizable work

**Architecture:**
1. **Planners** (1-3 Haiku workers): Decompose task → write `plan.json`
2. **Executors** (5-10 Haiku workers): Execute tasks in parallel from plan
3. **Coordination:** Filesystem locks (`task_locks/task_N.lock`)

**Benefits:**
- 10x parallelization (100 tasks ÷ 10 workers = 10x faster)
- 90% cost savings (all Haiku workers vs. sequential Sonnet)
- Scales linearly (more tasks → more workers)

## Key Insights for API Service Design

### 1. CLI Invocation Pattern
```bash
# Read prompt from file
prompt=$(cat prompt.txt)

# Pass as argument (preserves TTY)
claude -p "$prompt" --model haiku --output-format json
```

**Reusable for API:**
- API receives prompt via HTTP/WebSocket
- Write to temp file
- Spawn Claude process with read-then-pass pattern
- Stream output back to client
- Parse JSON for token usage

### 2. Token Tracking Pattern
```python
# Spawn with JSON output
subprocess.Popen([
    "claude", "-p", prompt,
    "--model", model,
    "--output-format", "json"
], stdout=output_file)

# Parse output
with open(output_file) as f:
    data = json.load(f)
    tokens_used = data["usage"]["input_tokens"] + data["usage"]["output_tokens"]
```

**Reusable for API:**
- Every API request tracks tokens automatically
- Return token counts to client
- Aggregate usage per user/project
- Implement rate limiting based on budgets

### 3. Model Routing Pattern
```python
def select_model(task_complexity, budget_remaining):
    if task_complexity == "simple" or budget_remaining < 1000:
        return "haiku"  # 8x cheaper
    elif task_complexity == "medium":
        return "sonnet"
    else:
        return "opus"  # Use sparingly
```

**Reusable for API:**
- API clients specify task complexity
- Service auto-routes to appropriate model
- Automatic cost optimization
- Budget enforcement

### 4. Parallel Execution Pattern
```python
# Spawn multiple workers
workers = []
for task in tasks:
    worker = spawn_claude_worker(task, model="haiku")
    workers.append(worker)

# Monitor completion
for worker in workers:
    worker.wait()
```

**Reusable for API:**
- API accepts batch requests
- Spawn parallel Claude sessions
- Aggregate results
- Return combined response

## Cost Comparison: Orchestrator vs. Manual Claude Code

**Scenario:** Build 10 features for a SaaS app

**Manual (single Claude session):**
- 1 session doing all work sequentially
- Sonnet model for everything
- Reads entire codebase multiple times
- Estimated: 150,000 tokens × $0.003/1K = $450

**Orchestrator (multi-worker parallel):**
- 5 parallel workers (Wave 1) + 3 workers (Wave 2) + 2 workers (Wave 3)
- Model routing: 70% Haiku, 25% Sonnet, 5% Opus
- Delegation: Helpers gather context, main workers execute
- Estimated: 60,000 tokens
  - 42,000 Haiku × $0.0004/1K = $16.80
  - 15,000 Sonnet × $0.003/1K = $45
  - 3,000 Opus × $0.015/1K = $45
  - Total: $106.80

**Savings: $450 - $107 = $343 (76% cheaper!)**

## Applicability to API Service

**What works for API:**
✅ CLI invocation pattern (read-then-pass)
✅ Token tracking via JSON output
✅ Model routing for cost optimization
✅ Parallel execution for throughput
✅ Budget management and circuit breakers

**What needs adaptation:**
⚠️ Filesystem coordination (use database/redis instead)
⚠️ Terminal spawning (use background processes instead)
⚠️ Git branching (optional for non-code use cases)
⚠️ Daemon architecture (use API server event loop)

**New requirements for API:**
- HTTP/WebSocket endpoint layer
- Request queuing and priority
- Multi-tenant isolation
- Streaming response support
- Authentication and rate limiting

## Next Steps for API Design

1. **Design API endpoints** that map to Claude CLI invocations
2. **Choose coordination mechanism** (Redis, PostgreSQL, filesystem)
3. **Implement worker pool** for parallel Claude session management
4. **Build token tracking** and budget enforcement
5. **Create client libraries** for easy integration
6. **Test with prototype** applications

## References

- **Source Code**: `~/claude-code-api-research/claude-code-orchestrator/`
- **Orchestrator README**: `../claude-code-orchestrator/README.md`
- **Worker Daemon**: `../claude-code-orchestrator/.claude/worker-daemon.py`
- **Launcher Script**: `../claude-code-orchestrator/claude-orch.sh`
- **Master Prompt**: `../claude-code-orchestrator/.claude/master-prompt.md`
