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

    model_config = SettingsConfigDict(env_prefix="CLAUDE_API_")


# Singleton — import and use directly
settings = Settings()
