---
created: 2026-01-30T13:40:00Z
updated: 2026-01-30T13:40:00Z
type: design
status: brainstorming
---

# Claude Code API Service - Architecture Design Brainstorm

## Vision

Create a **flexible, reusable local service** that acts as an API abstraction layer over Claude Code CLI, enabling any prototype or application to use Claude Code as their LLM provider with minimal setup.

## Core Value Propositions

### 1. **Use Your Claude Code Max Subscription**
- No separate API costs
- All calls go through existing subscription
- Same rate limits/billing as CLI usage
- Cost optimization via model routing (Haiku 8x cheaper than Sonnet)

### 2. **Rapid Prototyping**
- Drop-in LLM provider for any app
- No infrastructure setup needed
- Just HTTP/WebSocket endpoints
- Client libraries for common languages

### 3. **Intelligent Cost Management**
- Automatic model routing (simple→Haiku, complex→Sonnet/Opus)
- Token budget enforcement
- Usage tracking per project/user
- Circuit breakers to prevent runaway costs

### 4. **Multi-Agent Capabilities**
- Parallel execution (multiple Claude sessions)
- Task coordination patterns
- Worker pool management
- Swarm mode for bulk operations

## Architecture Options

### Option 1: Simple REST API Wrapper

**Concept:** Single HTTP server wrapping Claude CLI calls

```
[Client App] → HTTP Request → [API Server] → Claude CLI → Response
```

**Pros:**
- Simple to implement
- Easy to use (standard HTTP)
- Works with any client language
- Familiar pattern for developers

**Cons:**
- Blocking (one request at a time)
- No streaming responses
- Limited parallelism

**Tech Stack:**
- FastAPI (Python) for HTTP server
- SQLite for tracking/queue
- Background workers for Claude sessions

**Endpoints:**
```
POST /v1/completions
  Body: { prompt, model, max_tokens }
  Response: { completion, tokens_used, cost }

GET /v1/usage
  Response: { total_tokens, cost, by_model }

POST /v1/batch
  Body: { prompts: [...], model }
  Response: { completions: [...] }
```

### Option 2: WebSocket Streaming Service

**Concept:** Real-time bidirectional communication with streaming

```
[Client App] ←→ WebSocket ←→ [API Server] ←→ Claude CLI (streaming)
```

**Pros:**
- Streaming responses (tokens as generated)
- Real-time updates
- Long-lived connections
- Better UX for chat interfaces

**Cons:**
- More complex implementation
- WebSocket handling overhead
- Connection management

**Tech Stack:**
- FastAPI + WebSockets
- Redis for pub/sub messaging
- Process pool for Claude sessions

**Protocol:**
```json
// Client → Server
{
  "type": "prompt",
  "id": "req_123",
  "model": "haiku",
  "content": "Explain quantum computing"
}

// Server → Client (streaming)
{
  "type": "token",
  "id": "req_123",
  "token": "Quantum"
}

{
  "type": "complete",
  "id": "req_123",
  "tokens_used": 156
}
```

### Option 3: gRPC High-Performance Service

**Concept:** Binary protocol for low-latency, high-throughput

```
[Client App] → gRPC → [API Server] → Claude CLI → Response
```

**Pros:**
- Fastest performance
- Efficient binary protocol
- Bidirectional streaming
- Code generation for clients

**Cons:**
- More complex for web clients
- Steeper learning curve
- Binary debugging harder

**Tech Stack:**
- Python gRPC server
- Protocol buffers
- Multi-process worker pool

### Option 4: Message Queue-Based Async Service

**Concept:** Decouple requests via queue for scalability

```
[Client] → Queue (RabbitMQ/Redis) → [Workers] → Claude CLI → Results Queue → [Client]
```

**Pros:**
- Highly scalable
- Natural load balancing
- Resilient (retry on failure)
- Priority queuing

**Cons:**
- More infrastructure
- Async complexity
- Eventual consistency

**Tech Stack:**
- Redis for queuing
- Celery for task distribution
- Multiple worker processes

## Recommended Hybrid Architecture

**Combine REST + WebSocket for flexibility:**

```
                    ┌─────────────────┐
                    │  Claude Code    │
                    │  API Service    │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼─────┐      ┌─────▼──────┐     ┌─────▼─────┐
    │   REST   │      │ WebSocket  │     │  Worker   │
    │ Endpoint │      │  Endpoint  │     │   Pool    │
    └──────────┘      └────────────┘     └─────┬─────┘
                                                │
                                         ┌──────▼──────┐
                                         │   Redis     │
                                         │  (Queue +   │
                                         │   Cache)    │
                                         └─────────────┘
```

### Components

#### 1. **API Server (FastAPI)**
- REST endpoints for simple requests
- WebSocket endpoint for streaming chat
- Authentication middleware
- Rate limiting

#### 2. **Worker Pool**
- Manages Claude CLI processes
- Model routing logic
- Token tracking
- Budget enforcement

#### 3. **Redis**
- Request queue (async processing)
- Token usage cache
- Session state (for WebSocket)
- Rate limit counters

#### 4. **SQLite/PostgreSQL**
- Usage history
- Budget configs per project
- API key management

## API Design

### REST Endpoints

```python
# Single completion
POST /v1/chat/completions
{
  "model": "haiku|sonnet|opus",  # or "auto" for routing
  "messages": [
    {"role": "system", "content": "You are..."},
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 1000,
  "temperature": 0.7,
  "project_id": "my-prototype"  # For budget tracking
}

Response:
{
  "id": "cmpl_123",
  "choices": [{
    "message": {"role": "assistant", "content": "Hi!"},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 8,
    "total_tokens": 23,
    "cost_usd": 0.00092
  }
}

# Batch processing
POST /v1/batch
{
  "requests": [
    {"model": "haiku", "prompt": "Task 1"},
    {"model": "haiku", "prompt": "Task 2"}
  ],
  "parallel": true  # Run concurrently
}

# Usage tracking
GET /v1/usage?project_id=my-prototype&period=month

# Model routing test
POST /v1/route
{
  "task_description": "Simple data extraction",
  "context_size": 500
}
Response: {"recommended_model": "haiku"}
```

### WebSocket Protocol

```javascript
// Connect
ws = new WebSocket('ws://localhost:8080/v1/stream');

// Send request
ws.send(JSON.stringify({
  type: 'chat',
  model: 'sonnet',
  messages: [{role: 'user', content: 'Explain AI'}]
}));

// Receive streaming tokens
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'token') {
    console.log(msg.content);  // Stream to UI
  } else if (msg.type === 'done') {
    console.log('Tokens used:', msg.usage.total_tokens);
  }
};
```

## Worker Pool Implementation

### Process Pool Manager

```python
class ClaudeWorkerPool:
    def __init__(self, max_workers=5):
        self.workers = []
        self.queue = Queue()

    def submit(self, prompt, model="haiku"):
        """Submit task to pool"""
        task_id = generate_id()

        # Write prompt to temp file
        prompt_file = f"/tmp/claude_{task_id}.txt"
        with open(prompt_file, 'w') as f:
            f.write(prompt)

        # Spawn Claude process
        proc = subprocess.Popen([
            "claude", "-p", "$(cat {})".format(prompt_file),
            "--model", model,
            "--output-format", "json"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.workers.append({
            'id': task_id,
            'process': proc,
            'model': model,
            'started': time.time()
        })

        return task_id

    def get_result(self, task_id):
        """Get completed result"""
        worker = self.find_worker(task_id)
        stdout, stderr = worker['process'].communicate()

        # Parse JSON output
        result = json.loads(stdout)

        return {
            'completion': result.get('response'),
            'usage': result.get('usage'),
            'cost': result.get('total_cost_usd')
        }
```

## Model Routing Logic

```python
def auto_select_model(prompt: str, context_size: int = 0) -> str:
    """Intelligently route to cheapest viable model"""

    # Simple heuristics (can be enhanced with ML)
    if len(prompt) < 100 and "simple" in prompt.lower():
        return "haiku"  # 8x cheaper

    if context_size > 10000:
        return "opus"  # Best for large context

    # Check for complexity keywords
    complex_keywords = ["analyze", "architect", "design", "debug"]
    if any(kw in prompt.lower() for kw in complex_keywords):
        return "sonnet"

    return "haiku"  # Default to cheapest
```

## Budget Management

### Per-Project Budgets

```python
class BudgetManager:
    def __init__(self):
        self.budgets = {}  # project_id -> budget config

    def check_budget(self, project_id: str, estimated_tokens: int) -> bool:
        """Check if request fits within budget"""
        config = self.budgets.get(project_id)
        if not config:
            return True  # No limit

        current_usage = get_usage(project_id, period='month')
        projected = current_usage + estimated_tokens

        return projected <= config['monthly_limit']

    def track_usage(self, project_id: str, tokens: int, cost: float):
        """Record usage"""
        usage_db.insert({
            'project_id': project_id,
            'timestamp': datetime.now(),
            'tokens': tokens,
            'cost': cost
        })
```

## Client Library Example

### Python Client

```python
from claude_code_api import ClaudeClient

# Initialize
client = ClaudeClient(
    base_url="http://localhost:8080",
    api_key="your-key",
    project_id="my-prototype"
)

# Simple completion
response = client.complete(
    "Explain async/await in Python",
    model="auto"  # Auto-route to best model
)
print(response.content)
print(f"Cost: ${response.cost:.4f}")

# Streaming chat
for token in client.stream("Write a poem about AI"):
    print(token, end='', flush=True)

# Batch processing
results = client.batch([
    "Task 1: Analyze this data",
    "Task 2: Generate summary",
    "Task 3: Create report"
], parallel=True)
```

### JavaScript Client

```javascript
import { ClaudeCodeAPI } from 'claude-code-api';

const client = new ClaudeCodeAPI({
  baseURL: 'http://localhost:8080',
  projectId: 'my-prototype'
});

// Simple request
const response = await client.complete({
  prompt: 'Explain promises in JS',
  model: 'haiku'
});
console.log(response.content);

// Streaming
client.stream('Write a story about robots')
  .on('token', (token) => console.log(token))
  .on('done', (usage) => console.log('Tokens:', usage.total));
```

## Deployment Options

### Local Development
```bash
# Start service
python claude_api_server.py --port 8080

# Background service
pm2 start claude_api_server.py
```

### Docker Compose
```yaml
version: '3.8'
services:
  api:
    image: claude-code-api:latest
    ports:
      - "8080:8080"
    environment:
      - CLAUDE_PATH=/usr/local/bin/claude
      - MAX_WORKERS=5
    volumes:
      - ./data:/data

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

## Use Case Examples

### 1. **Chatbot Prototype**
```python
# Web chatbot using the API
@app.post("/chat")
async def chat_endpoint(message: str):
    response = claude_client.complete(
        f"User: {message}\nAssistant:",
        model="haiku"  # Fast and cheap for chat
    )
    return {"reply": response.content}
```

### 2. **Code Analysis Tool**
```python
# Analyze codebase
def analyze_code(file_path: str):
    with open(file_path) as f:
        code = f.read()

    analysis = claude_client.complete(
        f"Analyze this code for bugs:\n{code}",
        model="sonnet"  # Better for analysis
    )
    return analysis.content
```

### 3. **Batch Document Processing**
```python
# Process multiple documents in parallel
documents = load_documents()

results = claude_client.batch([
    f"Summarize: {doc}" for doc in documents
], parallel=True, model="haiku")

for doc, summary in zip(documents, results):
    save_summary(doc.id, summary.content)
```

### 4. **Multi-Agent Workflow**
```python
# Spawn multiple specialized agents
agents = {
    'planner': claude_client.spawn_agent(
        "You are a task planning agent",
        model="sonnet"
    ),
    'executor': claude_client.spawn_agent(
        "You are a task execution agent",
        model="haiku"
    ),
    'reviewer': claude_client.spawn_agent(
        "You are a quality review agent",
        model="opus"
    )
}

# Coordinate workflow
plan = agents['planner'].execute("Plan feature X")
result = agents['executor'].execute(f"Execute: {plan}")
review = agents['reviewer'].execute(f"Review: {result}")
```

## Implementation Roadmap

### Phase 1: MVP (2 weeks)
- [ ] Basic REST API (FastAPI)
- [ ] Single-worker Claude CLI wrapper
- [ ] Token tracking
- [ ] Simple authentication

### Phase 2: Core Features (2 weeks)
- [ ] Worker pool (parallel execution)
- [ ] Model auto-routing
- [ ] Budget management
- [ ] Usage analytics

### Phase 3: Advanced (2 weeks)
- [ ] WebSocket streaming
- [ ] Batch processing
- [ ] Redis caching
- [ ] Client libraries (Python, JS)

### Phase 4: Production Ready (2 weeks)
- [ ] Docker deployment
- [ ] Monitoring/logging
- [ ] Rate limiting
- [ ] Documentation

## Cost Analysis

### Comparison: Direct API vs. This Service

**Scenario:** Prototype chatbot, 1000 requests/day

**Option A: Anthropic API Direct**
- All requests to Claude 3 Haiku
- 1000 req × 500 tokens avg × $0.25/1M = $0.125/day
- Monthly: $3.75

**Option B: Claude Code API Service**
- Uses Claude Code Max subscription ($20/month)
- Same 1000 requests
- Cost: $0 additional (included in subscription)
- **Savings: $3.75/month**

**Break-even:** Service pays for itself at ~200 requests/day

### Enhanced Savings with Model Routing

**With intelligent routing:**
- 80% requests → Haiku (simple queries)
- 15% requests → Sonnet (medium complexity)
- 5% requests → Opus (complex reasoning)

**Direct API cost:**
- 800 × 500 × $0.25/1M = $0.10
- 150 × 500 × $3/1M = $0.225
- 50 × 500 × $15/1M = $0.375
- **Total: $0.70/day = $21/month**

**Claude Code service:**
- All included in $20/month subscription
- **Savings: ~$1/month + flexibility**

## Next Steps

1. **Build MVP** (Phase 1)
   - FastAPI server with basic endpoints
   - Single worker Claude CLI integration
   - SQLite for tracking

2. **Test with Prototype**
   - Simple chatbot UI
   - Measure latency, throughput
   - Validate cost savings

3. **Iterate Based on Feedback**
   - Add features as needed
   - Optimize performance
   - Improve developer experience

4. **Document & Share**
   - API documentation
   - Client library examples
   - Deployment guides

## Open Questions

- **Authentication:** API keys, JWT tokens, or both?
- **Multi-tenancy:** Isolate projects/users how?
- **Caching:** Cache responses for identical prompts?
- **Rate limiting:** Per project, per user, or both?
- **Monitoring:** Prometheus, custom dashboard, or both?
- **Model updates:** How to handle new Claude models?
- **Error handling:** Retry logic, fallback models?

## References

- **Analysis Document**: `./01-Analysis-Claude-Code-Orchestrator.md`
- **Orchestrator Source**: `../claude-code-orchestrator/`
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Claude Code CLI**: https://docs.anthropic.com/en/docs/claude-code
