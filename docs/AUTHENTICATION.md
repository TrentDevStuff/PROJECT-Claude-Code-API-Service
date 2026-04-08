# Authentication & Rate Limiting (INIT-008)

## Overview

The Claude Code API Service now requires API key authentication for all protected endpoints. This provides:

- **Security**: Only authorized clients can access the API
- **Rate Limiting**: Prevents abuse with per-key request limits
- **Project Tracking**: API keys are tied to project IDs for budget management

## API Key Format

All API keys follow the format: `cc_<40 hex characters>`

Example: `cc_a1b2c3d4e5f6789012345678901234567890abcd`

## Generating API Keys

### Using CLI (Recommended)

```bash
# Provision a persistent key for a service (get-or-create)
claude-api keys provision my-service

# Quiet mode — returns just the key (for scripts and service startup)
export CLAUDE_API_KEY=$(claude-api keys provision my-service -q)

# Keys are stored at ~/.claude-api/keys/<service-id>.key
# Subsequent calls return the existing key if still valid
claude-api keys provision my-service   # Returns same key

# Force create a new key
claude-api keys provision my-service --force

# Manual key creation (without local persistence)
claude-api keys create --project-id my-project --profile enterprise

# Manual creation with persistence
claude-api keys create --project-id my-project --save-as my-project

# View stored keys
claude-api keys store-list
```

### Using Python

```python
from src.auth import AuthManager

auth_manager = AuthManager(db_path="data/auth.db")

# Generate a key with default rate limit (100 req/min)
api_key = auth_manager.generate_key(project_id="my-project")

# Generate a key with custom rate limit
api_key = auth_manager.generate_key(
    project_id="my-project",
    rate_limit=200  # 200 requests per minute
)

print(f"API Key: {api_key}")
```

## Using API Keys

### HTTP Headers

All protected endpoints require a Bearer token in the Authorization header:

```
Authorization: Bearer cc_a1b2c3d4e5f6789012345678901234567890abcd
```

### Python Client

```python
import requests

api_key = "cc_a1b2c3d4e5f6789012345678901234567890abcd"
headers = {"Authorization": f"Bearer {api_key}"}

response = requests.post(
    "http://localhost:8080/v1/chat/completions",
    headers=headers,
    json={
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "haiku"
    }
)
```

### cURL

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer cc_a1b2c3d4e5f6789012345678901234567890abcd" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "model": "haiku"
  }'
```

## Protected Endpoints

The following endpoints require authentication:

- `POST /v1/chat/completions` - Chat completions
- `POST /v1/batch` - Batch processing
- `GET /v1/usage` - Usage statistics
- `POST /v1/route` - Model routing recommendations

## Unprotected Endpoints

These endpoints do NOT require authentication:

- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /docs` - API documentation

## Rate Limiting

### How It Works

- Rate limits are enforced per API key
- Window size: 60 seconds (1 minute)
- Default limit: 100 requests per minute
- Configurable per key

### Rate Limit Response

When rate limit is exceeded, the API returns:

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

HTTP Status Code: `429 Too Many Requests`

### Checking Rate Limit

```python
from src.auth import AuthManager

auth_manager = AuthManager(db_path="data/auth.db")

# This also increments the counter
allowed = auth_manager.check_rate_limit(api_key)

if not allowed:
    print("Rate limit exceeded!")
```

## Key Management

### Revoking Keys

```python
from src.auth import AuthManager

auth_manager = AuthManager(db_path="data/auth.db")
success = auth_manager.revoke_key(api_key)

if success:
    print("Key revoked successfully")
```

### Getting Key Info

```python
info = auth_manager.get_key_info(api_key)

print(f"Project ID: {info['project_id']}")
print(f"Rate Limit: {info['rate_limit']}")
print(f"Created: {info['created_at']}")
print(f"Last Used: {info['last_used_at']}")
print(f"Revoked: {info['revoked']}")
```

### Cleanup Old Rate Limit Records

```python
# Remove rate limit records older than 24 hours
deleted = auth_manager.cleanup_old_rate_limits(hours=24)
print(f"Deleted {deleted} old records")
```

## Database Schema

### api_keys Table

```sql
CREATE TABLE api_keys (
    key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    rate_limit INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    revoked BOOLEAN NOT NULL DEFAULT 0
);
```

### rate_limits Table

```sql
CREATE TABLE rate_limits (
    api_key TEXT NOT NULL,
    window_start TIMESTAMP NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (api_key, window_start),
    FOREIGN KEY (api_key) REFERENCES api_keys(key) ON DELETE CASCADE
);
```

## Error Responses

### Invalid API Key

```json
{
  "detail": "Invalid or revoked API key"
}
```

HTTP Status Code: `401 Unauthorized`

### Rate Limit Exceeded

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

HTTP Status Code: `429 Too Many Requests`

### Missing Authorization Header

```json
{
  "detail": "Not authenticated"
}
```

HTTP Status Code: `403 Forbidden`

## Testing

See `tests/test_auth.py` for comprehensive test examples.

### Running Tests

```bash
# Run auth tests only
python -m pytest tests/test_auth.py -v

# Run all tests
python -m pytest tests/ -v
```

## Security Best Practices

1. **Never commit API keys** to version control
2. **Store keys securely** in environment variables or secrets management
3. **Rotate keys periodically** for enhanced security
4. **Use different keys** for different environments (dev, staging, prod)
5. **Monitor usage** to detect anomalies
6. **Revoke compromised keys** immediately

## Future Enhancements

- [ ] API key rotation mechanism
- [ ] Key expiration dates
- [ ] Usage analytics dashboard
- [ ] IP allowlisting per key
- [ ] Webhook notifications for rate limit events
- [ ] Admin UI for key management
