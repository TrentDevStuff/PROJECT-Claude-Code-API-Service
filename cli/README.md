# Claude Code API Service CLI

Command-line interface for managing and monitoring the Claude Code API Service.

## Installation

```bash
# From repository root
pip install -e .

# Verify installation
claude-api --help
claude-api version
```

## Quick Start

```bash
# Check if service is running
claude-api health ping

# View full service status
claude-api service status

# List API keys
claude-api keys list

# Create a new API key
claude-api keys create --project-id my-project --profile enterprise

# Run endpoint tests
claude-api test all --key YOUR_API_KEY
```

## Command Reference

### Service Management (`claude-api service`)

**Start the service:**
```bash
claude-api service start                    # Start in foreground
claude-api service start --background       # Start in background
claude-api service start --logs             # Start and tail logs
```

**Stop the service:**
```bash
claude-api service stop                     # Graceful shutdown (30s timeout)
claude-api service stop --force             # Force kill if needed
```

**Check status:**
```bash
claude-api service status                   # Full status with metrics
```

**Other:**
```bash
claude-api service restart                  # Restart the service
claude-api service logs --follow            # Tail logs (planned feature)
```

### Health Checks (`claude-api health`)

**Full health check:**
```bash
claude-api health check                     # Check all components
claude-api health check --verbose           # Detailed component status
```

**Dependency check:**
```bash
claude-api health deps                      # Verify Redis, Claude CLI, agents, skills
```

**Quick ping:**
```bash
claude-api health ping                      # Fast service response check
```

### API Key Management (`claude-api keys`)

**Create a key:**
```bash
claude-api keys create \\
  --project-id my-app \\
  --profile enterprise \\
  --rate-limit 100 \\
  --name "Production Key"

# Output formats
claude-api keys create --project-id test --output json
claude-api keys create --project-id test --output env
```

**List keys:**
```bash
claude-api keys list                        # List all keys
claude-api keys list --project-id my-app    # Filter by project
claude-api keys list --active-only          # Show only active keys
```

**Manage permissions:**
```bash
# View permissions
claude-api keys permissions cc_abc123...

# Change profile
claude-api keys permissions cc_abc123... --set-profile pro

# Update max cost
claude-api keys permissions cc_abc123... --max-cost 5.00
```

**Revoke a key:**
```bash
claude-api keys revoke cc_abc123...         # With confirmation
claude-api keys revoke cc_abc123... --force # Skip confirmation
```

**Test a key:**
```bash
claude-api keys test cc_abc123...           # Verify if key is valid
```

### Agent Discovery (`claude-api agents`)

**List all agents:**
```bash
claude-api agents list --key cc_abc123...              # List all available agents
claude-api agents list --model haiku --key cc_abc123... # Filter by model (haiku, sonnet, opus)
claude-api agents list --json --key cc_abc123...       # JSON output
```

**Show agent details:**
```bash
claude-api agents info workflow-sync-agent --key cc_abc123...
```

**Search agents:**
```bash
claude-api agents search workflow --key cc_abc123...   # Search by keyword
```

### Skill Discovery (`claude-api skills`)

**List all skills:**
```bash
claude-api skills list --key cc_abc123...              # List all available skills
claude-api skills list --json --key cc_abc123...       # JSON output
```

**Show skill details:**
```bash
claude-api skills info semantic-text-matcher --key cc_abc123...
```

**Search skills:**
```bash
claude-api skills search text --key cc_abc123...       # Search by keyword
```

### Process (`claude-api process`)

**Send a prompt via /v1/process (AI Services compatible endpoint):**
```bash
# Send with defaults (anthropic/haiku, SDK path)
claude-api process send "Summarize this text" --key cc_abc123...

# Specify provider and model
claude-api process send "Hello" --provider openai --model gpt-4 --key cc_abc123...

# Use CLI execution path (slower, supports tools/agents)
claude-api process send "List files" --use-cli --key cc_abc123...

# With system message and max tokens
claude-api process send "Translate to French" \
  --system "You are a translator" \
  --max-tokens 500 \
  --key cc_abc123...

# JSON output
claude-api process send "Hello" --json --key cc_abc123...
```

**Smoke test:**
```bash
claude-api process test --key cc_abc123...             # Test SDK path
claude-api process test --use-cli --key cc_abc123...   # Test CLI path
```

### Providers (`claude-api providers`)

**List available providers:**
```bash
claude-api providers list                              # Table output
claude-api providers list --json                       # JSON output
```

**Show models for a provider:**
```bash
claude-api providers models anthropic                  # Model details
claude-api providers models openai --json              # JSON output
```

### Batch (`claude-api batch`)

**Run batch of prompts via /v1/batch:**
```bash
# From repeatable --prompt flags
claude-api batch run -p "Hello" -p "Goodbye" --key cc_abc123...

# From JSON file
claude-api batch run --file prompts.json --key cc_abc123...

# With specific model and timeout
claude-api batch run -p "Task 1" -p "Task 2" \
  --model sonnet --timeout 60 --key cc_abc123...

# Pipe from stdin
echo '["Prompt 1", "Prompt 2"]' | claude-api batch run --key cc_abc123...
```

### Route (`claude-api route`)

**Get model recommendation:**
```bash
claude-api route recommend "Simple greeting" --key cc_abc123...
claude-api route recommend "Architect a microservices system" \
  --context-size 5000 --key cc_abc123...
claude-api route recommend "Debug this code" --json --key cc_abc123...
```

### Testing (`claude-api test`)

**Test individual endpoints:**
```bash
# Chat completion
claude-api test completion \\
  --model haiku \\
  --prompt "Hello!" \\
  --key cc_abc123...

# Process endpoint (SDK path)
claude-api test process --key cc_abc123...

# Process endpoint (CLI path)
claude-api test process --use-cli --key cc_abc123...

# Agentic task
claude-api test task \\
  --description "List Python files" \\
  --tools "Bash,Glob" \\
  --key cc_abc123...

# Agent discovery
claude-api test agents --key cc_abc123...

# Skill discovery
claude-api test skills --key cc_abc123...
```

**Run all tests (5 endpoints):**
```bash
claude-api test all --key cc_abc123...
```

### Configuration (`claude-api config-*`)

**View configuration:**
```bash
claude-api config-show                      # Show current config
```

**Validate configuration:**
```bash
claude-api config-validate                  # Verify dependencies
```

### Usage Analytics (`claude-api usage`)

**Usage summary (fully functional):**
```bash
claude-api usage summary --key cc_abc123...                # Monthly summary (default)
claude-api usage summary --period day --key cc_abc123...   # Daily summary
claude-api usage summary --period week --key cc_abc123...  # Weekly summary
claude-api usage summary --json --key cc_abc123...         # JSON output
```

*Note: The following commands are placeholders - full implementation requires API enhancements*

```bash
claude-api usage by-project
claude-api usage by-model
claude-api usage costs
claude-api usage export --output usage.csv
```

### Worker Pool (`claude-api workers`)

*Note: These commands are placeholders - full implementation requires API enhancements*

```bash
claude-api workers status
claude-api workers list
claude-api workers clear-queue
claude-api workers kill WORKER_ID
```

### Task Management (`claude-api tasks`)

*Note: These commands are placeholders - full implementation requires API enhancements*

```bash
claude-api tasks list --status running
claude-api tasks get TASK_ID
claude-api tasks cancel TASK_ID
claude-api tasks logs TASK_ID
```

## Configuration File

The CLI auto-detects the service directory, but you can configure it manually:

**Location:** `~/.claude-api/config.yaml`

```yaml
service:
  directory: /path/to/claude-code-api-service
  port: 8006
  host: 0.0.0.0
  auto_start: false

cli:
  default_output: table  # table, json, text
  color: auto            # auto, always, never
  verbose: false
```

## Output Formats

Most commands support multiple output formats:

```bash
# Table (default) - human-readable
claude-api keys list

# JSON - for scripting
claude-api keys list --json

# Text - simple output
claude-api keys create --output text
```

## Shell Completion

Install shell completion for faster CLI usage:

```bash
# Bash
claude-api --install-completion bash

# Zsh
claude-api --install-completion zsh
```

## Common Workflows

### Starting the Service for First Time

```bash
# 1. Check dependencies
claude-api health deps

# 2. Start service
claude-api service start --background

# 3. Wait a moment, then check status
claude-api service status

# 4. Create an API key
claude-api keys create --project-id test --profile enterprise

# 5. Test endpoints
claude-api test all --key YOUR_KEY
```

### Debugging Issues

```bash
# Check if service is responding
claude-api health ping

# Full health check
claude-api health check --verbose

# View service status
claude-api service status

# Check dependencies
claude-api health deps

# Restart service if needed
claude-api service restart
```

### API Key Rotation

```bash
# List current keys
claude-api keys list

# Create new key
claude-api keys create --project-id my-app --profile enterprise

# Update application to use new key
# (manual step in your application)

# Test new key
claude-api keys test NEW_KEY

# Revoke old key
claude-api keys revoke OLD_KEY
```

## Troubleshooting

**"Service is not running"**
```bash
claude-api service start --background
```

**"Port 8006 already in use"**
```bash
# Check what's using the port
lsof -i :8006

# Stop the service if it's already running
claude-api service stop

# Or use a different port
claude-api service start --port 8007
```

**"Redis: not running"**
```bash
# Start Redis
brew services start redis  # macOS with Homebrew
# or
redis-server --daemonize yes
```

**"Claude CLI: not found"**
```bash
# Install Claude Code CLI
# Visit: https://docs.anthropic.com/en/docs/claude-code
```

**"API key is invalid"**
```bash
# Verify key exists
claude-api keys list

# Create new key if needed
claude-api keys create --project-id test
```

## Integration with Claude Code Agents

The CLI is designed to be easily invoked by Claude Code agents. Example agent workflow:

```python
# In a Claude Code agent session:

# 1. Check if service is running
run("claude-api health ping")

# 2. If not running, start it
if not_running:
    run("claude-api service start --background")
    time.sleep(2)

# 3. Create API key for user
result = run("claude-api keys create --project-id test --output json")
api_key = parse_json(result)["key"]

# 4. Test endpoints
run(f"claude-api test all --key {api_key}")

# 5. Report to user
report(f"Service ready at http://localhost:8006")
report(f"API Key: {api_key}")
```

## See Also

- **API Documentation**: http://localhost:8006/docs (when service is running)
- **Main README**: ../README.md
- **Service Configuration**: ~/.claude-api/config.yaml
- **PID File**: ~/.claude-api/service.pid
