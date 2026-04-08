---
created: 2026-01-30T13:40:00Z
updated: 2026-01-30T13:40:00Z
type: quick-reference
---

# Quick Start Guide

## What's in This Effort

### Research Documents

1. **`01-Analysis-Claude-Code-Orchestrator.md`** (9,000+ words)
   - Deep dive into how orchestrator uses Claude Code CLI
   - CLI invocation patterns explained
   - Token tracking mechanisms
   - Model routing and cost optimization
   - Filesystem-based coordination
   - Git safety and branching strategies
   - Complete code examples with line references

2. **`02-API-Service-Architecture-Brainstorm.md`** (7,000+ words)
   - Vision and value propositions
   - 4 architecture options evaluated:
     - REST API wrapper
     - WebSocket streaming service
     - gRPC high-performance
     - Message queue async
   - Recommended hybrid REST + WebSocket approach
   - Detailed API endpoint designs
   - Client library examples (Python, JavaScript)
   - Implementation roadmap (4 phases)
   - Cost analysis and comparisons
   - Use case examples

### Reference Code

**`../claude-code-orchestrator/`** - Complete working orchestrator system

Key files to study:
- `.claude/worker-daemon.py` - Worker spawning and lifecycle management
- `claude-orch.sh` - Launcher with model selection
- `.claude/master-prompt.md` - 42KB system prompt for orchestrator
- `.claude/QUICK_REFERENCE.md` - Orchestrator command cheat sheet

## Key Takeaways

### How to Use Claude Code Programmatically

```bash
# Read prompt from file (preserves TTY)
prompt=$(cat prompt.txt)

# Invoke Claude with model selection and JSON output
claude -p "$prompt" --model haiku --output-format json > output.json

# Parse token usage
cat output.json | jq '.usage.total_tokens'
```

### Cost Optimization Formula

- **Haiku**: 1x cost (baseline) - Use for simple tasks
- **Sonnet**: 3.75x cost - Use for medium complexity
- **Opus**: 18.75x cost - Use sparingly for complex reasoning

**Strategy:** Route 70-80% of work to Haiku → 60-70% cost savings

### Token Tracking Pattern

```python
import subprocess
import json

# Spawn with JSON output
result = subprocess.run([
    "claude", "-p", prompt,
    "--model", "haiku",
    "--output-format", "json"
], capture_output=True, text=True)

# Parse usage
data = json.loads(result.stdout)
tokens = data["usage"]["input_tokens"] + data["usage"]["output_tokens"]
cost = data["total_cost_usd"]
```

### Parallel Execution Pattern

```python
# Spawn multiple Claude sessions
workers = []
for task in tasks:
    worker = subprocess.Popen([
        "claude", "-p", task,
        "--model", "haiku",
        "--output-format", "json"
    ], stdout=subprocess.PIPE)
    workers.append(worker)

# Collect results
results = [w.communicate() for w in workers]
```

## Proposed API Service

### Architecture

```
Client Apps
    ↓
FastAPI Server (REST + WebSocket)
    ↓
Worker Pool Manager
    ↓
Claude CLI Processes (parallel)
    ↓
Redis (caching, queue) + SQLite (usage tracking)
```

### Sample Endpoints

```python
# Simple completion
POST /v1/chat/completions
{
  "model": "auto",  # Auto-route to best model
  "messages": [...],
  "project_id": "my-prototype"
}

# Batch processing
POST /v1/batch
{
  "requests": [...],
  "parallel": true
}

# Usage tracking
GET /v1/usage?project_id=my-prototype
```

### Client Library Example

```python
from claude_code_api import ClaudeClient

client = ClaudeClient(
    base_url="http://localhost:8080",
    project_id="my-prototype"
)

# Auto-routed completion
response = client.complete(
    "Explain async/await",
    model="auto"
)
print(response.content)
print(f"Cost: ${response.cost:.4f}")
```

## Implementation Roadmap

### Phase 1: MVP (2 weeks)
- Basic REST API with FastAPI
- Single-worker Claude CLI wrapper
- Token tracking with SQLite
- Simple API key authentication

### Phase 2: Core Features (2 weeks)
- Worker pool for parallel execution
- Model auto-routing logic
- Budget management per project
- Usage analytics dashboard

### Phase 3: Advanced (2 weeks)
- WebSocket streaming support
- Batch processing endpoints
- Redis caching layer
- Python & JavaScript client libraries

### Phase 4: Production (2 weeks)
- Docker deployment
- Monitoring and logging
- Rate limiting
- Comprehensive documentation

## Next Actions

1. **Read the analysis document** to understand Claude Code CLI patterns
2. **Review architecture brainstorm** to evaluate design options
3. **Build MVP** using FastAPI
4. **Test with simple prototype** (chatbot or tool)
5. **Iterate based on learnings**

## Quick Commands

### Explore Orchestrator
```bash
cd ~/claude-code-api-research/claude-code-orchestrator

# Read system prompt
cat .claude/master-prompt.md

# Study worker daemon
cat .claude/worker-daemon.py

# Check launcher script
cat claude-orch.sh
```

### Test Claude Code CLI
```bash
# Simple test
echo "Explain quantum computing in 50 words" | \
  claude -p "$(cat -)" --model haiku --output-format json

# With file
echo "You are a helpful assistant" > prompt.txt
claude -p "$(cat prompt.txt)" --model haiku
```

### Start API Development
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn redis pydantic

# Create basic server
# (See architecture doc for full code)
```

## Cost Calculator

**Formula:**
```
monthly_cost = (requests_per_day × 30 × avg_tokens × model_cost_per_1k) / 1000

# Example: 1000 requests/day, 500 tokens avg, Haiku model
monthly_cost = (1000 × 30 × 500 × 0.00025) / 1000 = $3.75

# With Claude Code API service: $0 (included in $20/month subscription)
```

## Resources

- **This Effort**: `~/claude-code-api-research/EFFORT-Claude-Code-API-Research/`
- **Orchestrator Repo**: `~/claude-code-api-research/claude-code-orchestrator/`
- **Claude Code Docs**: https://docs.anthropic.com/en/docs/claude-code
- **FastAPI Tutorial**: https://fastapi.tiangolo.com/tutorial/

## Questions to Explore

- **Authentication:** How to secure the API? (API keys, JWT, OAuth?)
- **Multi-tenancy:** How to isolate projects/users?
- **Caching:** Should we cache identical prompts?
- **Monitoring:** What metrics matter most?
- **Error handling:** Retry logic? Fallback models?
- **Scaling:** How many parallel workers can we sustain?

---

**Current Status:** Phase 1 Analysis Complete (10%)
**Next Milestone:** MVP API Service Implementation
