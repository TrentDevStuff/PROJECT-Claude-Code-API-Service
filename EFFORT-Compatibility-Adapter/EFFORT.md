---
type: effort
effort_id: EFFORT-Compatibility-Adapter
project: PROJECT-Claude-Code-API-Service
status: planning
priority: medium
progress: 0%
created: 2026-02-16T12:00:00Z
last_updated: 2026-02-16T12:00:00Z
linked_goal: null
---

# EFFORT: Compatibility Adapter Completion

## Overview

Stress-test and complete the `/v1/process` compatibility endpoint so all downstream services (playground-backend, ai-services-memory, ai-rag-services, advancedmd-mcp) can rely on it as a drop-in replacement for ai-service (port 8000).

The adapter exists (`src/compatibility_adapter.py`) and the async budget fix was applied (commit a9224fe), but it hasn't been systematically validated against all consumer patterns.

## Scope

### In Scope

1. **API surface audit** -- Compare `/v1/process` request/response schema to ai-service's actual API
2. **Consumer pattern testing** -- Test with each downstream service's actual request payloads
3. **Error handling** -- Ensure error responses match ai-service format (status codes, error schema)
4. **Edge cases** -- Streaming, large payloads, multimodal content field, tool_calls passthrough
5. **Integration tests** -- Automated tests covering all consumer patterns
6. **Documentation** -- Compatibility matrix: what works, what's stubbed, what's unsupported

### Out of Scope

- Adding new ai-service features (tools, memory, media)
- Performance parity with ai-service
- Multi-provider routing to actual OpenAI/Google (just maps to Claude)

## Plan

### Phase 1: Audit

- Read ai-service's actual `/v1/process` endpoint code (if accessible) or reverse-engineer from consumer usage
- Document every field consumers actually send
- Identify gaps between our adapter and real usage

### Phase 2: Consumer Payload Testing

For each downstream service:
- Capture actual request payloads (from logs or .env inspection)
- Submit them to `/v1/process`
- Verify response format matches expectations

| Consumer | Port | Key Fields Used |
|----------|------|-----------------|
| playground-backend | 8001 | messages, model_name, provider, max_tokens |
| ai-services-memory | 8082 | system_message, user_message, provider |
| ai-rag-services | 8002 | messages, system_message, max_tokens |
| advancedmd-mcp | 8080 | messages, provider, model_name |

### Phase 3: Fix & Test

- Fix any gaps found in Phase 1-2
- Write integration tests for each consumer pattern
- Add to CI

## Success Criteria

- [ ] All 4 downstream services work through `/v1/process` without errors
- [ ] Error responses match ai-service format
- [ ] Integration tests cover all consumer patterns
- [ ] Compatibility matrix documented

## Related

- File: `src/compatibility_adapter.py`
- Fix: commit a9224fe (async budget manager calls)
- Consumers: playground-backend, ai-services-memory, ai-rag-services, advancedmd-mcp
