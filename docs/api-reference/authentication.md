# Authentication

All API requests require authentication with an API key.

## Getting Your API Key

Since this is a self-hosted service, you create API keys locally using the CLI or Python.

### Using CLI (Recommended)

```bash
# Install CLI first
pip install -e .

# Provision a persistent key for a service (get-or-create)
claude-api keys provision my-app

# Quiet mode for scripts — just the key
export CLAUDE_API_KEY=$(claude-api keys provision my-app -q)

# Keys stored at ~/.claude-api/keys/<service-id>.key
# Persist across service restarts; revalidated on each call

# Manual creation (without local persistence)
claude-api keys create --project-id my-app --profile enterprise

# Manual creation with persistence
claude-api keys create --project-id my-app --save-as my-app

# Create with custom rate limit
claude-api keys create --project-id test --profile pro --rate-limit 50

# View stored keys
claude-api keys store-list

# List all keys in server database
claude-api keys list

# View a key's permissions
claude-api keys permissions YOUR_KEY
```

### Using Python

```python
from src.auth import AuthManager
from src.permission_manager import PermissionManager

# Create key
auth = AuthManager()
api_key = auth.generate_key("my-project", rate_limit=100)

# Set permissions
perm = PermissionManager()
perm.apply_default_profile(api_key, "enterprise")

print(f"API Key: {api_key}")
```

## Using Your API Key

### HTTP Header (Recommended)

Include in the `Authorization` header:

```bash
curl -X POST http://localhost:8006/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

### Query Parameter

Fallback for WebSocket or special cases:

```bash
ws://localhost:8006/v1/stream?api_key=YOUR_API_KEY
```

### In Python Client

```python
from client import ClaudeClient

# Explicit API key
client = ClaudeClient(
    base_url="http://localhost:8006",
    api_key="YOUR_API_KEY"
)

# Or from environment variable
import os
client = ClaudeClient(
    base_url="http://localhost:8006",
    api_key=os.getenv("CLAUDE_API_KEY")
)
```

## API Key Security

### Best Practices

**Do:**
- Store keys in environment variables
- Use `.env` files (never commit to git)
- Create separate keys per application/environment
- Use minimum required permissions
- Rotate keys periodically

**Don't:**
- Commit keys to version control
- Expose in client-side code
- Share keys via email/chat
- Log or print API keys

### Securing Keys in Code

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Loads from .env file

api_key = os.getenv("CLAUDE_API_KEY")
if not api_key:
    raise ValueError("CLAUDE_API_KEY environment variable not set")

client = ClaudeClient(
    base_url="http://localhost:8006",
    api_key=api_key
)
```

### .env File Example

```bash
CLAUDE_API_KEY=cc_your_key_here
CLAUDE_API_URL=http://localhost:8006
```

Add to `.gitignore`:

```
.env
.env.local
.env.*.local
```

## API Key Permissions

Each API key has specific permissions:

- **Tools allowed**: Which tools can be used (Read, Grep, Bash, etc.)
- **Agents allowed**: Which agents can be spawned
- **Skills allowed**: Which skills can be invoked
- **Rate limits**: Requests per minute
- **Budget limit**: Maximum cost per task

Manage permissions with the CLI:

```bash
# View permissions
claude-api keys permissions YOUR_KEY

# Change profile
claude-api keys permissions YOUR_KEY --set-profile enterprise

# Update max cost
claude-api keys permissions YOUR_KEY --max-cost 5.00
```

Or with Python:

```python
from src.permission_manager import PermissionManager

perm = PermissionManager()

# Apply preset profile
perm.apply_default_profile(api_key, "enterprise")

# Or custom permissions
perm.set_profile(api_key, {
    "allowed_tools": ["Read", "Grep", "Bash"],
    "blocked_tools": ["Write"],
    "allowed_agents": ["company-workflow-analyst"],
    "max_cost_per_task": 0.50
})
```

## Permission Tiers

### Free

- Tools: Read, Grep (read-only)
- Agents: None
- Rate limit: 10 requests/minute
- Max cost: $0.10/task
- Timeout: 60 seconds

### Pro

- Tools: Read, Grep, Bash, Edit, Write
- Agents: Standard agents
- Rate limit: 100 requests/minute
- Max cost: $1.00/task
- Timeout: 300 seconds (5 minutes)

### Enterprise

- Tools: All
- Agents: All
- Skills: All
- Rate limit: Custom
- Max cost: Custom
- Timeout: Custom

## Error Responses

### 401 Unauthorized - Missing Key

```json
{
  "error": {
    "type": "authentication_error",
    "message": "Missing Authorization header"
  }
}
```

### 401 Unauthorized - Invalid Key

```json
{
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

### 403 Forbidden - Insufficient Permissions

```json
{
  "error": {
    "type": "permission_error",
    "message": "Tool 'Bash' is not allowed for this API key"
  }
}
```

### 429 Rate Limited

```json
{
  "error": {
    "type": "rate_limit_error",
    "message": "Rate limit exceeded. Reset in 60 seconds."
  }
}
```

## Revoking Keys

If a key is compromised:

```bash
# Using CLI
claude-api keys revoke YOUR_KEY

# Force without confirmation
claude-api keys revoke YOUR_KEY --force
```

Or with Python:

```python
from src.auth import AuthManager

auth = AuthManager()
auth.revoke_key("YOUR_KEY")
```

Revoked keys stop working immediately.

## Rate Limiting

The API enforces rate limits per API key. Headers indicate current status:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1672531200
```

When rate limited (429 response), implement backoff:

```python
import time
from client import RateLimitError

def retry_with_backoff(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn()
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"Rate limited, waiting {wait}s")
            time.sleep(wait)
```

## Token Budget

Track token usage and costs:

```python
response = client.complete("Test")

print(f"Tokens: {response.usage.total_tokens}")
print(f"Cost: ${response.cost:.4f}")
```

Set budgets to prevent overspend:

```python
result = client.agentic_task(
    description="Analyze code",
    max_cost=1.0  # Stop if exceeds $1.00
)
```

## Monitoring Usage

Check usage via API:

```bash
curl http://localhost:8006/v1/usage?project_id=my-app \
  -H "Authorization: Bearer YOUR_KEY"
```

Or CLI:

```bash
claude-api usage summary --period week
claude-api usage by-project
```

## Troubleshooting

### "Invalid API key"

```bash
# List existing keys
claude-api keys list

# Create new key
claude-api keys create --project-id test --profile enterprise
```

### "Permission denied"

```bash
# Check permissions
claude-api keys permissions YOUR_KEY

# Upgrade tier
claude-api keys permissions YOUR_KEY --set-profile enterprise
```

### "Rate limit exceeded"

Wait 60 seconds or implement exponential backoff (see above).
