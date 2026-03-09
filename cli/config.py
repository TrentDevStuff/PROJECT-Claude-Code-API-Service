"""Configuration management for CLI"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServiceConfig(BaseModel):
    """Service configuration"""

    directory: Path
    port: int = 8006
    host: str = "0.0.0.0"
    auto_start: bool = False


class CLIConfig(BaseModel):
    """CLI configuration"""

    default_output: str = "table"  # table, json, text
    color: str = "auto"  # auto, always, never
    verbose: bool = False


class Config(BaseModel):
    """Complete CLI configuration"""

    service: ServiceConfig
    cli: CLIConfig = Field(default_factory=CLIConfig)


class ConfigManager:
    """Manages CLI configuration with auto-detection"""

    def __init__(self):
        self.config_file = Path.home() / ".claude-api" / "config.yaml"
        self._config: Config | None = None

    def detect_service_directory(self) -> Path:
        """Auto-detect service directory"""
        # 1. Check environment variable
        if env_dir := os.getenv("CLAUDE_API_SERVICE_DIR"):
            path = Path(env_dir)
            if self._is_valid_service_dir(path):
                return path

        # 2. Check current directory
        cwd = Path.cwd()
        if self._is_valid_service_dir(cwd):
            return cwd

        # 3. Check common location
        home_dir = Path.home() / "claude-code-api-service"
        if self._is_valid_service_dir(home_dir):
            return home_dir

        raise FileNotFoundError(
            "Could not find Claude Code API Service directory. "
            "Set CLAUDE_API_SERVICE_DIR environment variable or run from service directory."
        )

    def _is_valid_service_dir(self, path: Path) -> bool:
        """Check if directory contains the service"""
        if not path.exists():
            return False
        return (path / "main.py").exists() and (path / "src").exists()

    def load(self) -> Config:
        """Load configuration (with auto-detection fallback)"""
        if self._config:
            return self._config

        # Try to load from config file
        if self.config_file.exists():
            with open(self.config_file) as f:
                data = yaml.safe_load(f)
                self._config = Config(**data)
                return self._config

        # Auto-detect service directory
        service_dir = self.detect_service_directory()

        # Create default config
        self._config = Config(service=ServiceConfig(directory=service_dir))

        return self._config

    def save(self, config: Config):
        """Save configuration to file"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

        self._config = config

    def get_service_url(self) -> str:
        """Get service URL"""
        config = self.load()
        return f"http://{config.service.host}:{config.service.port}"


# Singleton instance
config_manager = ConfigManager()
