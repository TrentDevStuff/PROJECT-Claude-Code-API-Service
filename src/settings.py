"""
Application settings via pydantic-settings.

All settings can be overridden with environment variables prefixed with CLAUDE_API_.
Example: CLAUDE_API_PORT=8080, CLAUDE_API_LOG_LEVEL=DEBUG
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with environment variable overrides."""

    port: int = 8006
    max_workers: int = 5
    db_path: str = "data/budgets.db"
    auth_db_path: str = "data/auth.db"
    redis_url: str = "redis://localhost:6379"
    log_level: str = "INFO"
    log_json: bool = True
    shutdown_timeout: int = 30
    mcp_config: str = ""  # Path to MCP server config JSON (passed to claude --mcp-config)

    # SDK retry and circuit breaker
    sdk_max_retries: int = 4
    sdk_timeout_seconds: float = 60.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 30.0

    # Tool calling passthrough.
    # When true AND the request includes `tools`, /v1/chat/completions routes
    # to the SDK path (DirectCompletionClient → Anthropic Messages API) so the
    # tool_calls / tool_result round trip is preserved. When false, tool
    # definitions are ignored and the request flattens to the CLI path.
    # Downstream services that rely on OpenAI-style tool calling require this
    # to be true — see .env for the deployed value.
    tool_passthrough_enabled: bool = False

    # Default execution path for /v1/process when the request omits `use_cli`.
    # Recommended setting per environment:
    #   Dev / local:   True  (CLI path — uses your Claude Max subscription, no per-token cost)
    #   Production:    False (SDK path — uses ANTHROPIC_API_KEY, reliable + scalable but pay-per-token)
    # Callers can always override per-request by sending `use_cli` explicitly.
    # Override the default via CLAUDE_API_DEFAULT_USE_CLI=(true|false) in the env.
    # NOTE: this flag only gates /v1/process. /v1/chat/completions routes by
    # (request.tools + tool_passthrough_enabled); see that flag's docstring.
    default_use_cli: bool = True

    # Prompt caching for the SDK (Anthropic Messages API) path.
    # When true, DirectCompletionClient annotates the tools + system prefix and
    # the message history with cache_control markers so repeated requests pay
    # ~10% of the base input cost on cached tokens. Cache writes cost ~1.25×
    # for the 5-minute TTL (break-even at 2 requests sharing the prefix).
    # Safe default: no behavior change, only cost reduction. Disable only for
    # debugging or workloads where no two requests ever share a prefix.
    prompt_caching_enabled: bool = True

    model_config = SettingsConfigDict(env_prefix="CLAUDE_API_")


# Singleton — import and use directly
settings = Settings()
