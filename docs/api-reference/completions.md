# Text Completions API

The Completions API provides simple text-to-text generation with Claude.

## Execution Paths

This endpoint (`/v1/chat/completions`) always uses the **CLI path**, which spawns a Claude CLI subprocess. This gives full access to Claude Code features (tools, agents, skills, MCP servers, working directory context) but incurs 3-8s of CLI cold start overhead.

For simple prompt-to-completion without Claude Code features, use `/v1/process` instead, which defaults to the **SDK path** (~50ms overhead). See the [Execution Paths Guide](../guides/execution-paths.md) for details.

| Endpoint | Default Path | Overhead | Features |
|----------|-------------|----------|----------|
| `/v1/chat/completions` | CLI always | 3-8s cold start | Full Claude Code (tools, agents, MCP) |
| `/v1/process` | SDK (default) | ~50ms | Simple completions only |
| `/v1/process` + `use_cli: true` | CLI | 3-8s cold start | Full Claude Code |

## Endpoint

```
POST /v1/chat/completions
```

## Request

### Headers

```
Authorization: Bearer sk-proj-your-key
Content-Type: application/json
```

### Body

```json
{
  "model": "sonnet",
  "messages": [
    {
      "role": "user",
      "content": "Explain quantum computing in simple terms"
    }
  ],
  "max_tokens": 1000,
  "temperature": 0.7
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | No | Model to use: `haiku`, `sonnet`, `opus`. Auto-selected if omitted. |
| `messages` | array | Yes | Array of message objects with `role` and `content`. |
| `max_tokens` | integer | No | Maximum tokens to generate (default: 1000, max: 4000). |
| `temperature` | float | No | Randomness (0.0-2.0, default: 0.7). Lower = more deterministic. |
| `top_p` | float | No | Nucleus sampling (0.0-1.0, default: 1.0). |
| `stop` | array | No | Stop sequences. Generation stops when any is encountered. |

## Response

```json
{
  "id": "msg_123abc",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Quantum computing harnesses quantum mechanical phenomena..."
    }
  ],
  "model": "sonnet",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 15,
    "output_tokens": 287,
    "total_tokens": 302,
    "cost": 0.0045
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique message ID. |
| `type` | string | Always `"message"`. |
| `role` | string | Always `"assistant"`. |
| `content` | array | Array of content blocks. |
| `content[].type` | string | Content type: `"text"`. |
| `content[].text` | string | Generated text. |
| `model` | string | Model used (may differ from request if auto-selected). |
| `stop_reason` | string | Why generation stopped: `"end_turn"`, `"stop_sequence"`, `"max_tokens"`. |
| `usage.input_tokens` | integer | Tokens in input. |
| `usage.output_tokens` | integer | Tokens in output. |
| `usage.total_tokens` | integer | Total tokens. |
| `usage.cost` | float | Cost in USD. |

## Examples

### Basic Completion

```bash
curl -X POST http://localhost:8006/v1/chat/completions \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

Response:
```json
{
  "id": "msg_123",
  "content": [
    {"type": "text", "text": "2+2 equals 4."}
  ],
  "usage": {
    "input_tokens": 10,
    "output_tokens": 8,
    "total_tokens": 18,
    "cost": 0.0003
  }
}
```

### Multi-turn Conversation

```bash
curl -X POST http://localhost:8006/v1/chat/completions \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is Python?"},
      {"role": "assistant", "content": "Python is a programming language..."},
      {"role": "user", "content": "What are its main uses?"}
    ]
  }'
```

## Error Responses

### 400 Bad Request

```json
{
  "error": {
    "type": "invalid_request_error",
    "message": "Missing required field: messages"
  }
}
```

### 401 Unauthorized

```json
{
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

### 429 Rate Limited

```json
{
  "error": {
    "type": "rate_limit_error",
    "message": "Rate limit exceeded. Retry after 60 seconds."
  }
}
```

### 500 Server Error

```json
{
  "error": {
    "type": "server_error",
    "message": "Internal server error. Try again later."
  }
}
```

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (invalid/missing API key) |
| 403 | Forbidden (insufficient permissions) |
| 429 | Rate limited (too many requests) |
| 500 | Server error (internal issue) |

## Rate Limiting

Rate limits are per API key and depend on your plan:

- **Free**: 10 requests/minute
- **Pro**: 100 requests/minute
- **Enterprise**: Custom limits

Response headers indicate rate limit status:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1672531200
```

## Pricing

Pricing is per token and depends on model:

| Model | Input | Output |
|-------|-------|--------|
| Haiku | $0.03 / 1M | $0.15 / 1M |
| Sonnet | $0.15 / 1M | $0.75 / 1M |
| Opus | $3.00 / 1M | $15.00 / 1M |

## Python Client Example

```python
from client import ClaudeClient

client = ClaudeClient(api_key="sk-proj-your-key")

response = client.complete(
    prompt="Explain machine learning",
    model="sonnet",
    max_tokens=500
)

print(response.content)
print(f"Cost: ${response.usage.cost:.4f}")
```
