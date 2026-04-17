# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Role

`claude-code-api-service` is the **LLM routing proxy** between the agent runtime (`claude-agents`, port 8005) and Anthropic. It runs on **port 8006** and exposes two primary request paths:

- **CLI path** — spawns `claude` subprocesses via `WorkerPool` (slow cold start, full tool/agent/skill access)
- **SDK path** — direct Anthropic Messages API via `DirectCompletionClient` (fast, simple completions with optional tool calling)

Both paths share: budget tracking, auth, permission profiles, audit logging, circuit breakers, and error classification.

All endpoints require Bearer token auth. Keys are stored in `~/.claude-api/keys/<service-id>.key` (persistent) and in the auth DB at `data/auth.db`.

## Common Commands

```bash
# Run server (foreground)
python main.py                       # Uses port from CLAUDE_API_PORT env or 8006

# Run server via CLI wrapper
claude-api service start --background
claude-api service stop
claude-api service status
claude-api health ping

# Tests
pytest                               # Full suite (expects 80%+ coverage per pytest.ini)
pytest tests/test_worker_pool.py -v  # Single test file
pytest tests/test_api.py::test_name  # Single test
pytest --cov=src --cov-report=html   # Coverage report

# Lint / format
black .
ruff check .
ruff check --fix .

# Docker
docker-compose up -d
docker-compose logs -f
```

**Settings:** All env vars use prefix `CLAUDE_API_` (e.g., `CLAUDE_API_PORT`, `CLAUDE_API_MAX_WORKERS`, `CLAUDE_API_TOOL_PASSTHROUGH_ENABLED`). See `src/settings.py` for the full list.

**Entry point:** `main.py` (FastAPI app with lifespan manager) — not `src/api.py`. `main.py` wires up all services in `lifespan()` and calls `initialize_services()` / `initialize_auth()` / `initialize_websocket()` before yielding.

## Architecture

### Request Routing

```
POST /v1/chat/completions   (OpenAI format)
  ├─ tools present + TOOL_PASSTHROUGH_ENABLED → SDK path (DirectCompletionClient)
  └─ else                                     → CLI path (WorkerPool → claude subprocess)

POST /v1/process            (AI-services format, multi-provider compat layer)
  ├─ request.use_cli: true   → CLI path (WorkerPool)
  ├─ request.use_cli: false  → SDK path (DirectCompletionClient)
  └─ omitted                 → settings.default_use_cli
                                 (True in dev → CLI/Claude Max;
                                  False in prod → SDK/API key)

POST /v1/task               (agentic execution with agent/skill discovery)
  └─ always CLI path via AgenticExecutor (which uses WorkerPool)

POST /v1/batch              (parallel prompts → WorkerPool)
WS   /v1/stream             (streaming tokens via worker subprocess)
GET  /v1/capabilities       (scans ~/.claude/agents/ and ~/.claude/skills/)
GET  /v1/usage              (per-project token/cost stats from budget DB)
GET  /health, /ready        (deep health — reports worker pool, Redis, audit DB, circuit breakers)
```

### Service Graph (wired in `main.py` lifespan)

- **WorkerPool** (`src/worker_pool.py`) — thread pool spawning `claude -p` subprocesses. Classifies stderr into `rate_limited | overloaded | timeout | upstream_error | auth_error | cli_error`. Tasks carry `TaskResult` with `error_category`, `retry_after`, `upstream_status`.
- **DirectCompletionClient** (`src/direct_completion.py`) — Anthropic SDK wrapper. Applies `cache_control` markers to the tools+system prefix and the last user turn when `CLAUDE_API_PROMPT_CACHING_ENABLED` is on (default True); cache creation / read token counts are in every `sdk_direct_completion` log record as `cache_creation_tokens` / `cache_read_tokens` / `cache_hit_ratio`. Returns the same `TaskResult` type as the CLI path so `_raise_for_failed_task()` can map errors uniformly.
- **BudgetManager** (`src/budget_manager.py`) — per-project token caps, usage in `data/budgets.db` (aiosqlite).
- **AuthManager** (`src/auth.py`) — API key store in `data/auth.db`. `verify_api_key` dep returns `project_id`.
- **PermissionManager** (`src/permission_manager.py`) — profile-based tool/agent/skill allowlists enforced before `/v1/task` executes.
- **AuditLogger** (`src/audit_logger.py`) — security events to SQLite.
- **CircuitBreakers** — one per path (`sdk_circuit`, `cli_circuit`). Failures increment; when tripped, requests return 503 with `Retry-After`.
- **ErrorTracker** (`src/error_tracker.py`) — rolling 5-min window of categorized errors for `/health`.
- **RedisCache** (`src/cache.py`) — optional; non-fatal if unavailable.
- **RequestIDMiddleware** (`src/middleware.py`) — pure ASGI, wraps CORS.

### Error Classification → HTTP Status

`src/api.py::_raise_for_failed_task()` maps `TaskResult.error_category` to HTTP status and propagates `X-Error-Category`, `X-Upstream-Status`, and `Retry-After` headers. CLI stderr classification lives in `worker_pool._classify_cli_stderr()`; SDK exceptions are classified in `direct_completion.py`. Keep the two classifiers aligned — downstream clients rely on consistent categories.

### Agent/Skill Discovery

`src/agent_discovery.py` scans `~/.claude/agents/*.md` (YAML frontmatter) and `~/.claude/skills/*/skill.json` on demand. Results are cached in-process. The `AgenticExecutor` injects enriched agent/skill metadata (description, tools, model, `Task(...)` / `Skill(...)` invocation examples) into the prompt before handing off to the worker pool. Skills marked `user_interface: agent-wrapped` are excluded from `/v1/capabilities`.

### Tool Translation (SDK path)

`src/tool_translation.py` converts between OpenAI tool format (what clients send) and Anthropic tool format (what the SDK expects), and back for responses. `src/compatibility_adapter.py` does the same for the AI-services `/v1/process` schema (multi-provider request/response mapping).

### Claude CLI Subprocess Hygiene

`main.py` strips `CLAUDECODE` and `CLAUDE_CODE_SESSION` from `os.environ` on startup. This is required when the service is launched from inside a Claude Code session — otherwise spawned `claude -p` subprocesses inherit the parent session state and deadlock on nested sessions. Don't undo this. See `INVESTIGATION-Claude-CLI-Nested-Session-Block.md`.

### uvicorn Event Loop

`main.py` forces `loop="asyncio"` (not `uvloop`). The original rationale was a suspected uvloop/GIL interaction with the `WorkerPool` monitor thread, but the actual bug behind the "service hangs after first request" symptom turned out to be a reentrant-lock deadlock in `CircuitBreaker.status()` (fixed in `src/circuit_breaker.py`). The `asyncio` loop pin is retained as a conservative default — switch to `uvloop` only after re-running the lock-contention tests under load.

## Key Directories

- `src/` — all service code (flat, no submodules)
- `cli/` — `claude-api` command-line tool (installed via `pip install -e .` → `[project.scripts]`)
- `client/` — Python client library (`ClaudeClient`) — separately packageable
- `tests/` — pytest suite, `conftest.py` provides shared fixtures
- `EFFORT-*/` — per-initiative planning docs (orchestration state, not runtime code)
- `INBOX/`, `OUTBOX/` — Forgg coordination protocol message folders
- `docs/` — user-facing documentation (API reference, getting started, etc.)
- `data/` — runtime SQLite DBs (budgets, auth) — gitignored

## Inter-Project Coordination (Forgg Protocol)

This project participates in the Forgg inter-AI coordination protocol as **CCA** (claude-code-api-service). Onboarded 2026-04-10 for `EFFORT-Cross-Service-Observability` (FORGG Cycle 4).

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

**Project codes:** FRG (FORGG arbiter), PPL, FCL, AGO, SSD, MAP, ACA (AI Claude Agents), AIS (AI Service), **CCA (this project)**
