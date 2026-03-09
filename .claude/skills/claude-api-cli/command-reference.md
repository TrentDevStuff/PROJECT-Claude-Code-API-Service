# Claude API CLI - Complete Command Reference

**Loaded on-demand for detailed command information.**

## Service Commands

### start
```bash
claude-api service start [OPTIONS]
```

**Options:**
- `--port PORT` - Override default port (8006)
- `--background / -b` - Run in background (detached)
- `--no-deps-check` - Skip dependency verification
- `--logs / -l` - Tail logs after starting

**What it does:**
1. Checks dependencies (Redis, Claude CLI, agents, skills)
2. Verifies port availability
3. Starts service process
4. Saves PID to `~/.claude-api/service.pid`

**Returns:**
- Service URL
- API docs URL
- PID (if background mode)

### stop
```bash
claude-api service stop [OPTIONS]
```

**Options:**
- `--force / -f` - Force kill if graceful shutdown fails
- `--timeout SECONDS` - Shutdown timeout (default: 30)

**What it does:**
1. Reads PID file
2. Sends SIGTERM (graceful shutdown)
3. Waits for process to exit
4. Force kills if timeout exceeded (with --force)
5. Removes PID file

### restart
```bash
claude-api service restart [OPTIONS]
```

**Options:**
- `--port PORT` - Override port

**What it does:**
1. Stops service (if running)
2. Waits 2 seconds
3. Starts service in background

### status
```bash
claude-api service status [OPTIONS]
```

**Options:**
- `--json` - Output as JSON

**Shows:**
- Running status (Yes/No)
- PID
- Port
- Uptime
- Memory usage
- CPU usage
- Health status
- Dependencies (Redis, agents, skills)

### logs
```bash
claude-api service logs [OPTIONS]
```

**Options:**
- `--lines / -n N` - Number of lines (default: 50)
- `--follow / -f` - Follow logs (tail -f style)
- `--level LEVEL` - Filter by level
- `--search PATTERN` - Search for pattern

**Note:** Currently placeholder - suggests running service in foreground for logs

---

## Health Commands

### check
```bash
claude-api health check [OPTIONS]
```

**Options:**
- `--json` - Output as JSON
- `--verbose / -v` - Detailed component status

**Checks:**
- API Service responding
- Redis connection (with ping time)
- Budget Manager operational
- Auth Manager operational
- Agent Discovery (count)
- Skill Discovery (count)

**Exit codes:**
- 0 - All healthy
- 1 - At least one component unhealthy

### deps
```bash
claude-api health deps
```

**Verifies:**
- Redis (status, port, memory usage)
- Claude CLI (version, path)
- Agents (location, count, sample list)
- Skills (location, count, sample list)

**Shows:**
- Detailed status for each dependency
- Installation instructions if missing
- Sample discoveries

### ping
```bash
claude-api health ping
```

**Quick check:**
- Hits `/health` endpoint
- Returns success if service responds
- Fast (< 1 second)

---

## API Key Commands

### create
```bash
claude-api keys create --project-id ID [OPTIONS]
```

**Required:**
- `--project-id / -p ID` - Project identifier

**Options:**
- `--profile PROFILE` - Permission profile (default: enterprise)
  - `free` - Read-only tools, no agents, $0.10/task
  - `pro` - Limited tools, security agents, $1.00/task
  - `enterprise` - All tools/agents/skills, $10.00/task
- `--rate-limit N` - Requests per minute (default: 100)
- `--name / -n NAME` - Friendly name
- `--output FORMAT` - Output format (text/json/env)

**Returns:**
- API key (cc_...)
- Project ID
- Profile
- Rate limit
- Permissions summary
- .env snippet

**Outputs:**
- `text` - Formatted output (default)
- `json` - JSON object
- `env` - Environment variable format

### list
```bash
claude-api keys list [OPTIONS]
```

**Options:**
- `--project-id / -p ID` - Filter by project
- `--active-only` - Show only active keys
- `--json` - Output as JSON

**Shows:**
- Key (truncated)
- Project ID
- Rate limit
- Created timestamp
- Total count

### revoke
```bash
claude-api keys revoke KEY [OPTIONS]
```

**Arguments:**
- `KEY` - API key or prefix to revoke

**Options:**
- `--force / -f` - Skip confirmation

**What it does:**
1. Confirms with user (unless --force)
2. Marks key as revoked in database
3. Key immediately stops working

### permissions
```bash
claude-api keys permissions KEY [OPTIONS]
```

**Arguments:**
- `KEY` - API key to inspect

**Options:**
- `--set-profile PROFILE` - Change profile
- `--max-cost COST` - Set max cost per task

**Shows:**
- Current profile
- Max cost per task
- Allowed tools (or all)
- Allowed agents (or all)
- Allowed skills (or all)
- Blocked tools (if any)

**Actions:**
- View permissions (no options)
- Change profile (--set-profile)
- Update max cost (--max-cost)

### test
```bash
claude-api keys test KEY
```

**Arguments:**
- `KEY` - API key to test

**What it does:**
- Validates key in database
- Checks if revoked
- Returns valid/invalid

---

## Test Commands

### completion
```bash
claude-api test completion [OPTIONS]
```

**Options:**
- `--model MODEL` - Model to test (haiku/sonnet/opus, default: haiku)
- `--prompt TEXT` - Custom prompt (default: "Hello!")
- `--key KEY` - API key to use

**What it does:**
1. Sends chat completion request
2. Measures response time
3. Shows response content (truncated)
4. Shows token usage and cost

**Output:**
- Request details
- Response time
- Status code
- Content preview
- Token counts
- Cost

### task
```bash
claude-api test task [OPTIONS]
```

**Options:**
- `--description TEXT` - Task description (default: "List Python files in src/")
- `--tools TOOLS` - Comma-separated tool list (default: "Bash,Glob")
- `--key KEY` - API key to use

**What it does:**
1. Creates agentic task
2. Waits for completion
3. Shows task ID, status, result
4. Shows duration and cost

**Output:**
- Task creation details
- Task ID
- Status
- Result summary
- Duration
- Cost

### agents
```bash
claude-api test agents [OPTIONS]
```

**Options:**
- `--key KEY` - API key to use

**What it does:**
1. Fetches `/v1/capabilities`
2. Extracts agents list
3. Shows count and samples

**Output:**
- Agent count
- Sample agent names (first 5)
- Models used

### skills
```bash
claude-api test skills [OPTIONS]
```

**Options:**
- `--key KEY` - API key to use

**What it does:**
1. Fetches `/v1/capabilities`
2. Extracts skills list
3. Shows count and samples

**Output:**
- Skill count
- Sample skill names (first 5)

### all
```bash
claude-api test all [OPTIONS]
```

**Options:**
- `--key KEY` - API key to use

**What it does:**
1. Tests GET /health
2. Tests GET /v1/capabilities
3. Tests POST /v1/chat/completions
4. Summarizes results

**Output:**
- Test results (passed/failed for each)
- Total percentage
- Exit code 0 if all pass, 1 if any fail

---

## Configuration Commands

### config-show
```bash
claude-api config-show
```

**Shows:**
- Config file location
- Service directory (auto-detected)
- Service port
- Service host
- CLI preferences

**Auto-detection order:**
1. `$CLAUDE_API_SERVICE_DIR` environment variable
2. Current directory (if contains main.py + src/)
3. `~/claude-code-api-service/`

### config-validate
```bash
claude-api config-validate
```

**Runs full dependency check:**
- Same as `claude-api health deps`
- Verifies all requirements
- Shows status of each

---

## Placeholder Commands

**These commands are implemented but require API enhancements:**

### usage
- `summary` - Usage summary
- `by-project` - Project breakdown
- `by-model` - Model breakdown
- `costs` - Cost breakdown
- `export` - Export usage data

### workers
- `status` - Worker pool status
- `list` - List active workers
- `clear-queue` - Clear pending tasks
- `kill WORKER_ID` - Kill specific worker

### tasks
- `list` - List tasks
- `get TASK_ID` - Get task details
- `cancel TASK_ID` - Cancel task
- `logs TASK_ID` - View task logs

**All placeholder commands:**
- Show what data they would display
- Indicate API enhancement needed
- Provide clear next steps

---

## Exit Codes

- `0` - Success
- `1` - Error or failure

---

## Environment Variables

**Service:**
- `PORT` - Override service port
- `CLAUDE_API_SERVICE_DIR` - Override service directory

**Usage:**
```bash
PORT=8006 claude-api service start
CLAUDE_API_SERVICE_DIR=/custom/path claude-api config-show
```

---

## Configuration File

**Location:** `~/.claude-api/config.yaml`

**Format:**
```yaml
service:
  directory: /path/to/service
  port: 8006
  host: 0.0.0.0
  auto_start: false

cli:
  default_output: table  # table, json, text
  color: auto            # auto, always, never
  verbose: false
```

**Created automatically** on first run with auto-detected values.

---

## Files & Locations

| File | Purpose |
|------|---------|
| `~/.claude-api/config.yaml` | CLI configuration |
| `~/.claude-api/service.pid` | Running service PID |
| `/path/to/service/data/auth.db` | API keys database |
| `/path/to/service/main.py` | Service entry point |

---

## Troubleshooting

### Service won't start
1. Check dependencies: `claude-api health deps`
2. Check port: `lsof -i :8006`
3. Check logs: Run service in foreground without `--background`

### API key doesn't work
1. Verify key exists: `claude-api keys list`
2. Test key: `claude-api keys test KEY`
3. Check permissions: `claude-api keys permissions KEY`

### Tests failing
1. Check service: `claude-api health ping`
2. Verify key: `claude-api keys test KEY`
3. Check profile: Enterprise profile needed for full access

### Can't find service
1. Set environment: `export CLAUDE_API_SERVICE_DIR=/path/to/service`
2. Or create config: `~/.claude-api/config.yaml`
3. Or run from service directory

---

## Integration Examples

### Python Script
```python
import subprocess
import json

# Start service
subprocess.run(["claude-api", "service", "start", "--background"])

# Create key
result = subprocess.run(
    ["claude-api", "keys", "create", "--project-id", "my-app", "--output", "json"],
    capture_output=True,
    text=True
)
key_data = json.loads(result.stdout)
api_key = key_data["key"]

# Test
subprocess.run(["claude-api", "test", "all", "--key", api_key])
```

### Bash Script
```bash
#!/bin/bash

# Health check
if ! claude-api health ping; then
    echo "Starting service..."
    claude-api service start --background
    sleep 2
fi

# Get or create key
KEY=$(claude-api keys list --json | jq -r '.[0].api_key' 2>/dev/null)

if [ -z "$KEY" ]; then
    echo "Creating API key..."
    KEY=$(claude-api keys create --project-id test --output json | jq -r '.key')
fi

# Run tests
claude-api test all --key "$KEY"
```

---

## Shell Completion

Install completion for your shell:

```bash
# Bash
claude-api --install-completion bash

# Zsh
claude-api --install-completion zsh

# Fish
claude-api --install-completion fish
```

Restart your shell after installation.

---

## For Full Documentation

See `cli/README.md` in the project root for:
- Complete usage guide
- Common workflows
- Troubleshooting
- Integration patterns
