---
created: 2026-01-31T10:17:13Z
updated: 2026-01-31T10:17:13Z
status: completed
priority: high
effort_id: EFFORT-CLI
project: claude-code-api-service
goal: Create comprehensive CLI for service management and monitoring
type: effort
---

# EFFORT-CLI: Claude Code API Service CLI

## Overview

Build a comprehensive command-line interface for the Claude Code API Service that enables efficient management, monitoring, and debugging. The CLI should be designed from Claude Code's perspective - providing the commands and information that an AI assistant needs to quickly help users manage their API service.

## Goals

1. **Service Management** - Start, stop, restart, check status, manage workers
2. **API Key Management** - Create, list, revoke, configure permissions
3. **Monitoring** - Health checks, logs, usage analytics, active tasks
4. **Budget Control** - View usage, set limits, track costs by project/model
5. **Testing** - Quick endpoint tests, agent/skill discovery validation
6. **Debugging** - Execution logs, worker pool inspection, security events

## Success Criteria

- ✅ Single `claude-api` command with intuitive subcommands
- ✅ Rich, formatted output (tables, JSON, human-readable)
- ✅ Non-blocking operations where appropriate
- ✅ Helpful error messages and suggestions
- ✅ Works seamlessly with Claude Code agent workflows
- ✅ Zero configuration (auto-detects service location)
- ✅ Comprehensive help text for all commands

## Scope

**In Scope:**
- CLI tool (`cli/claude_api.py` or similar)
- Service management commands
- API key management commands
- Monitoring and analytics commands
- Testing and validation commands
- Rich formatting library (Rich or Typer)
- Comprehensive documentation

**Out of Scope:**
- GUI/web interface (CLI only)
- Service installation/deployment (assumes service exists)
- Database migrations (use existing managers)
- New API features (CLI wraps existing functionality)

## Timeline

**Estimated Duration:** 2-3 days

**Phases:**
1. **Planning** - Detailed command design (this document)
2. **Foundation** - CLI framework, config loading, service detection
3. **Management Commands** - service, keys, workers, budgets
4. **Monitoring Commands** - health, logs, usage, analytics
5. **Testing Commands** - test endpoints, validate config
6. **Polish** - help text, error handling, output formatting
7. **Documentation** - README, examples, integration guide

## Dependencies

- Existing service components (auth, budget, worker pool, etc.)
- CLI framework (Click or Typer recommended)
- Rich library for formatting
- Requests library for HTTP calls

## Notes

The CLI should feel natural for Claude Code agents to invoke. Commands should:
- Return structured output (JSON option for parsing)
- Provide clear success/failure indicators
- Include context in error messages
- Support batch operations where useful
- Be idempotent where possible
