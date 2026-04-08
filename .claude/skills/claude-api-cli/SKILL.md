# Claude API CLI Skill

**Quick access to Claude Code API Service management via CLI.**

## When to Use This Skill

User wants to:
- Start/stop/check the API service
- Create or manage API keys
- Test API endpoints
- Check service health
- Verify dependencies (Redis, Claude CLI, agents, skills)

## Quick Commands

### Service Management
```bash
claude-api service start --background    # Start service
claude-api service stop                  # Stop service
claude-api service status                # Check status
```

### Health Checks
```bash
claude-api health ping                   # Quick check
claude-api health check                  # Full health check
claude-api health deps                   # Verify dependencies
```

### API Keys
```bash
# Provision a persistent key for a local service (get-or-create)
claude-api keys provision SERVICE_ID           # Interactive
claude-api keys provision SERVICE_ID -q        # Just the key (for scripts)
export CLAUDE_API_KEY=$(claude-api keys provision my-svc -q)

# Retrieve a stored key
claude-api keys get SERVICE_ID -q

# List stored keys with validity
claude-api keys store-list

# Manual creation (with optional persistence)
claude-api keys create --project-id PROJECT --profile PROFILE
claude-api keys create --project-id PROJECT --save-as SERVICE_ID

# List all keys in server database
claude-api keys list

# View permissions
claude-api keys permissions KEY_PREFIX
```

**Profiles:** `free`, `pro`, `enterprise`
**Key store:** `~/.claude-api/keys/<service-id>.key` (mode 600, persists across restarts)

### Agent/Skill Discovery
```bash
# List available agents
claude-api agents list --key API_KEY
claude-api agents list --model haiku --key API_KEY

# Agent details
claude-api agents info AGENT_NAME --key API_KEY
claude-api agents search KEYWORD --key API_KEY

# List available skills
claude-api skills list --key API_KEY

# Skill details
claude-api skills info SKILL_NAME --key API_KEY
claude-api skills search KEYWORD --key API_KEY
```

### Testing
```bash
# Test all endpoints (requires API key)
claude-api test all --key API_KEY

# Test specific endpoints
claude-api test completion --key API_KEY
claude-api test agents --key API_KEY
```

### Configuration
```bash
claude-api config-show                   # Show config
claude-api config-validate               # Verify dependencies
```

## Common Workflows

### User: "Is the service running?"
```bash
claude-api health ping
```

### User: "Start the service"
```bash
# Check dependencies first
claude-api health deps

# Start service
claude-api service start --background

# Verify it started
claude-api service status
```

### User: "I need an API key"
```bash
# Provision a persistent key (recommended)
claude-api keys provision PROJECT_NAME

# Or for scripts
export CLAUDE_API_KEY=$(claude-api keys provision PROJECT_NAME -q)
```

### User: "Test if everything works"
```bash
# If they have a key
claude-api test all --key THEIR_KEY

# If they need a key first
claude-api keys create --project-id test --profile enterprise
# Then use returned key for testing
```

### User: "What agents/skills are available?"
```bash
# List all agents with their models
claude-api agents list --key API_KEY

# Find agents for a specific task
claude-api agents search workflow --key API_KEY

# See detailed info about an agent
claude-api agents info workflow-sync-agent --key API_KEY

# Same for skills
claude-api skills list --key API_KEY
claude-api skills search text --key API_KEY
```

### User: "Why isn't it working?"
```bash
# Check service status
claude-api service status

# Check dependencies
claude-api health deps

# Full health check
claude-api health check

# Common issues:
# - Service not running → claude-api service start --background
# - Redis not running → brew services start redis (macOS)
# - Port in use → claude-api service stop, then start
```

## Output Handling

**Default:** Beautiful Rich tables (human-readable)

**JSON mode:** Add `--json` for parsing:
```bash
claude-api keys list --json
```

**Other formats:**
```bash
claude-api keys create --output env     # For .env files
claude-api keys create --output json    # For scripts
```

## Important Notes

**Service Location:**
- CLI auto-detects service directory
- Config: `~/.claude-api/config.yaml`
- PID file: `~/.claude-api/service.pid`

**Authentication:**
- Most endpoints require API key
- Test commands need `--key` option
- Keys never expire (manual revocation only)
- Keys persist in `~/.claude-api/keys/` (via `provision` command)
- `provision` validates stored keys against DB; auto-replaces revoked keys

**Placeholder Commands:**
- `usage`, `workers`, `tasks` - Need API enhancements
- These show what data they would display
- Clear messaging about required API work

## Error Messages

CLI provides helpful suggestions:
```
✗ Service is not running
  → Start with: claude-api service start
```

Follow the suggestions - they're accurate!

## For Detailed Reference

Read `command-reference.md` in this skill directory for:
- Complete command list
- All options and flags
- Troubleshooting guide
- Integration examples

## Script Usage

```python
# Execute CLI commands
result = subprocess.run(["claude-api", "health", "ping"], capture_output=True)

# Parse JSON output
result = subprocess.run(
    ["claude-api", "keys", "list", "--json"],
    capture_output=True,
    text=True
)
keys = json.loads(result.stdout)
```

## Summary

**Most common user needs:**
1. "Start the service" → `service start --background`
2. "Create API key" → `keys provision SERVICE_ID` (get-or-create with persistence)
3. "Is it working?" → `health check` or `test all --key KEY`
4. "Stop the service" → `service stop`

**Always check service status first if user reports issues.**

For comprehensive documentation: `cli/README.md` in project root.
