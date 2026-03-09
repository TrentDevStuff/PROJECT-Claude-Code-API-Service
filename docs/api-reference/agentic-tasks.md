# Agentic Tasks API

Execute complex multi-step tasks with Claude's agentic capabilities. Tasks can use tools, spawn agents, and invoke skills.

This endpoint always uses the **CLI path** (Claude CLI subprocess). The SDK path does not support tool use, agent spawning, or skill invocation. See [Execution Paths](../guides/execution-paths.md) for details.

## Endpoint

```
POST /v1/task
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
  "description": "Analyze src/api.py for security vulnerabilities",
  "allow_tools": ["Read", "Grep"],
  "allow_agents": ["security-auditor"],
  "timeout": 300,
  "max_cost": 1.0
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `description` | string | Yes | Natural language task description. |
| `allow_tools` | array | No | Tools to enable (e.g., `["Read", "Grep", "Bash"]`). |
| `allow_agents` | array | No | Agents to enable (e.g., `["security-auditor"]`). |
| `allow_skills` | array | No | Skills to enable (e.g., `["semantic-text-matcher"]`). |
| `timeout` | integer | No | Task timeout in seconds (default: 300, max: 600). |
| `max_cost` | float | No | Maximum cost in USD (default: 1.0). |
| `context` | object | No | Additional context (e.g., `{"project": "myapp", "language": "python"}`). |

## Response

```json
{
  "id": "task_123abc",
  "status": "completed",
  "description": "Analyze src/api.py for security vulnerabilities",
  "result": {
    "summary": "Found 3 security issues: SQL injection risk in query builder, missing CORS validation, hardcoded credentials",
    "issues": [
      {
        "severity": "high",
        "type": "sql_injection",
        "location": "src/api.py:145",
        "description": "User input not properly sanitized in query"
      }
    ]
  },
  "execution_log": [
    {
      "timestamp": "2026-01-30T12:00:00Z",
      "action": "tool_call",
      "tool": "Read",
      "file": "src/api.py",
      "status": "success"
    },
    {
      "timestamp": "2026-01-30T12:00:01Z",
      "action": "tool_call",
      "tool": "Grep",
      "pattern": "SELECT.*FROM",
      "status": "success"
    }
  ],
  "artifacts": [
    {
      "type": "file",
      "path": "security_audit_report.md",
      "size_bytes": 4521,
      "created_at": "2026-01-30T12:00:05Z"
    }
  ],
  "usage": {
    "input_tokens": 2500,
    "output_tokens": 1200,
    "total_tokens": 3700,
    "total_cost": 0.45
  },
  "created_at": "2026-01-30T12:00:00Z",
  "completed_at": "2026-01-30T12:00:10Z"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique task ID. |
| `status` | string | Task status: `"pending"`, `"running"`, `"completed"`, `"failed"`, `"timeout"`. |
| `description` | string | Original task description. |
| `result` | object | Task result (structure depends on task). |
| `execution_log` | array | Log of all actions taken. |
| `artifacts` | array | Generated files and artifacts. |
| `usage` | object | Token usage and cost. |
| `created_at` | string | ISO 8601 timestamp when task was created. |
| `completed_at` | string | ISO 8601 timestamp when task completed. |

## Examples

### Code Analysis Task

```bash
curl -X POST http://localhost:8006/v1/task \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Analyze our FastAPI application for security vulnerabilities",
    "allow_tools": ["Read", "Grep"],
    "allow_agents": ["security-auditor"],
    "timeout": 300,
    "max_cost": 1.0
  }'
```

### Documentation Generation Task

```bash
curl -X POST http://localhost:8006/v1/task \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Generate API documentation for all endpoints in src/api.py",
    "allow_tools": ["Read"],
    "allow_agents": ["documentation-generator"],
    "timeout": 300
  }'
```

### Test Generation Task

```bash
curl -X POST http://localhost:8006/v1/task \
  -H "Authorization: Bearer sk-proj-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Generate comprehensive test cases for the User model in src/models.py",
    "allow_tools": ["Read"],
    "allow_agents": ["test-generator"],
    "timeout": 300
  }'
```

## Available Tools

| Tool | Description | Capabilities |
|------|-------------|--------------|
| `Read` | Read file contents | Access file system (within sandbox) |
| `Grep` | Search file contents | Pattern matching with regex |
| `Bash` | Execute bash commands | Shell commands (sandboxed) |
| `Edit` | Modify files | Text editing |
| `Write` | Create files | File creation |
| `Glob` | Pattern-based file matching | Find files by pattern |

## Available Agents

| Agent | Description | Use Case |
|-------|-------------|----------|
| `security-auditor` | Security vulnerability analysis | Find security issues in code |
| `documentation-generator` | Auto-generate documentation | Create API docs, README files |
| `test-generator` | Generate test cases | Create unit/integration tests |
| `code-analyzer` | Analyze code quality | Suggest improvements |
| `performance-analyzer` | Identify bottlenecks | Optimize slow code |

## Available Skills

| Skill | Description | Output |
|-------|-------------|--------|
| `semantic-text-matcher` | Find semantically similar text | Similarity scores |
| `entity-mapper` | Map text to entity IDs | Standardized entities |
| `decision-framework` | Automated decision making | Decisions with confidence |

## Error Responses

### 400 Bad Request

```json
{
  "error": {
    "type": "invalid_request_error",
    "message": "Missing required field: description"
  }
}
```

### 403 Permission Denied

```json
{
  "error": {
    "type": "permission_error",
    "message": "Tool 'Bash' is not allowed for your API key"
  }
}
```

### 408 Timeout

```json
{
  "error": {
    "type": "timeout_error",
    "message": "Task exceeded 300 second timeout"
  }
}
```

### 429 Cost Exceeded

```json
{
  "error": {
    "type": "cost_exceeded_error",
    "message": "Task would exceed maximum cost of $1.00"
  }
}
```

## Python Client Example

```python
from client import ClaudeClient

client = ClaudeClient(api_key="sk-proj-your-key")

result = client.execute_task(
    description="Analyze our API for security vulnerabilities",
    allow_tools=["Read", "Grep"],
    allow_agents=["security-auditor"],
    timeout=300,
    max_cost=1.0
)

print(f"Status: {result.status}")
print(f"Summary: {result.result['summary']}")
print(f"Artifacts generated: {len(result.artifacts)}")
print(f"Cost: ${result.usage.total_cost:.4f}")

for artifact in result.artifacts:
    print(f"  - {artifact.path} ({artifact.size_bytes} bytes)")
```

## Polling for Results

For asynchronous task execution, poll the task status:

```bash
# Start task
curl -X POST http://localhost:8006/v1/task \
  -H "Authorization: Bearer sk-proj-your-key" \
  -d '{"description": "..."}' \
  > task.json

TASK_ID=$(jq -r .id task.json)

# Poll status
while true; do
  curl -X GET http://localhost:8006/v1/task/$TASK_ID \
    -H "Authorization: Bearer sk-proj-your-key"

  sleep 2
done
```
