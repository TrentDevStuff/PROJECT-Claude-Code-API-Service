"""
Permission Manager for API-key based access control.

Manages per-API-key permission profiles including:
- Tool, agent, and skill whitelists/blacklists
- Resource limits (CPU, memory, execution time)
- Cost limits per task
- Network and filesystem access controls
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PermissionProfile:
    """Permission profile for an API key"""

    api_key: str
    allowed_tools: list[str]
    blocked_tools: list[str]
    allowed_agents: list[str]
    allowed_skills: list[str]
    max_concurrent_tasks: int
    max_cpu_cores: float
    max_memory_gb: float
    max_execution_seconds: int
    max_cost_per_task: float
    network_access: bool
    filesystem_access: str  # 'none', 'readonly', 'readwrite'
    workspace_size_mb: int


@dataclass
class PermissionValidation:
    """Result of permission validation"""

    allowed: bool
    reason: str
    profile: PermissionProfile | None = None


# Default permission profiles
DEFAULT_PROFILES = {
    "free": {
        "allowed_tools": ["Read"],
        "blocked_tools": ["Write", "Edit", "Bash"],
        "allowed_agents": [],
        "allowed_skills": [],
        "max_concurrent_tasks": 1,
        "max_cpu_cores": 0.5,
        "max_memory_gb": 0.5,
        "max_execution_seconds": 60,
        "max_cost_per_task": 0.10,
        "network_access": False,
        "filesystem_access": "readonly",
        "workspace_size_mb": 50,
    },
    "pro": {
        "allowed_tools": ["Read", "Grep", "Glob", "Bash"],
        "blocked_tools": ["Write", "Edit"],
        "allowed_agents": ["security-auditor", "code-reviewer"],
        "allowed_skills": ["vulnerability-scanner", "code-analyzer"],
        "max_concurrent_tasks": 3,
        "max_cpu_cores": 1.0,
        "max_memory_gb": 1.0,
        "max_execution_seconds": 300,
        "max_cost_per_task": 1.00,
        "network_access": False,
        "filesystem_access": "readonly",
        "workspace_size_mb": 100,
    },
    "enterprise": {
        "allowed_tools": ["*"],  # All tools
        "blocked_tools": [],
        "allowed_agents": ["*"],  # All agents
        "allowed_skills": ["*"],  # All skills
        "max_concurrent_tasks": 10,
        "max_cpu_cores": 4.0,
        "max_memory_gb": 4.0,
        "max_execution_seconds": 600,
        "max_cost_per_task": 10.00,
        "network_access": True,
        "filesystem_access": "readwrite",
        "workspace_size_mb": 500,
    },
}


class PermissionManager:
    """
    Manages API key permissions and validates task requests.

    Uses the same database as BudgetManager (data/budgets.db) but manages
    the api_key_permissions table.
    """

    def __init__(self, db_path: str = "data/budgets.db"):
        """Initialize PermissionManager with database path"""
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create api_key_permissions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS api_key_permissions (
                api_key TEXT PRIMARY KEY,
                allowed_tools TEXT NOT NULL,
                blocked_tools TEXT NOT NULL,
                allowed_agents TEXT NOT NULL,
                allowed_skills TEXT NOT NULL,
                max_concurrent_tasks INTEGER DEFAULT 3,
                max_cpu_cores REAL DEFAULT 1.0,
                max_memory_gb REAL DEFAULT 1.0,
                max_execution_seconds INTEGER DEFAULT 300,
                max_cost_per_task REAL DEFAULT 1.00,
                network_access BOOLEAN DEFAULT 0,
                filesystem_access TEXT DEFAULT 'readonly',
                workspace_size_mb INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        conn.close()

    def get_profile(self, api_key: str) -> PermissionProfile | None:
        """
        Load permission profile from database.

        Args:
            api_key: API key to look up

        Returns:
            PermissionProfile if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT allowed_tools, blocked_tools, allowed_agents, allowed_skills,
                   max_concurrent_tasks, max_cpu_cores, max_memory_gb,
                   max_execution_seconds, max_cost_per_task, network_access,
                   filesystem_access, workspace_size_mb
            FROM api_key_permissions
            WHERE api_key = ?
        """,
            (api_key,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return PermissionProfile(
            api_key=api_key,
            allowed_tools=json.loads(row[0]),
            blocked_tools=json.loads(row[1]),
            allowed_agents=json.loads(row[2]),
            allowed_skills=json.loads(row[3]),
            max_concurrent_tasks=row[4],
            max_cpu_cores=row[5],
            max_memory_gb=row[6],
            max_execution_seconds=row[7],
            max_cost_per_task=row[8],
            network_access=bool(row[9]),
            filesystem_access=row[10],
            workspace_size_mb=row[11],
        )

    def set_profile(self, api_key: str, profile: dict[str, Any]):
        """
        Create or update permission profile.

        Args:
            api_key: API key to set profile for
            profile: Profile dictionary with permission settings
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO api_key_permissions (
                api_key, allowed_tools, blocked_tools, allowed_agents, allowed_skills,
                max_concurrent_tasks, max_cpu_cores, max_memory_gb,
                max_execution_seconds, max_cost_per_task, network_access,
                filesystem_access, workspace_size_mb
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                api_key,
                json.dumps(profile.get("allowed_tools", [])),
                json.dumps(profile.get("blocked_tools", [])),
                json.dumps(profile.get("allowed_agents", [])),
                json.dumps(profile.get("allowed_skills", [])),
                profile.get("max_concurrent_tasks", 3),
                profile.get("max_cpu_cores", 1.0),
                profile.get("max_memory_gb", 1.0),
                profile.get("max_execution_seconds", 300),
                profile.get("max_cost_per_task", 1.00),
                profile.get("network_access", False),
                profile.get("filesystem_access", "readonly"),
                profile.get("workspace_size_mb", 100),
            ),
        )

        conn.commit()
        conn.close()

    def apply_default_profile(self, api_key: str, profile_tier: str):
        """
        Apply a default profile (free, pro, or enterprise) to an API key.

        Args:
            api_key: API key to apply profile to
            profile_tier: One of 'free', 'pro', or 'enterprise'
        """
        if profile_tier not in DEFAULT_PROFILES:
            raise ValueError(f"Invalid profile tier: {profile_tier}")

        self.set_profile(api_key, DEFAULT_PROFILES[profile_tier])

    def validate_task_request(
        self,
        api_key: str,
        requested_tools: list[str] | None = None,
        requested_agents: list[str] | None = None,
        requested_skills: list[str] | None = None,
        timeout: int | None = None,
        max_cost: float | None = None,
    ) -> PermissionValidation:
        """
        Validate a task request against API key permissions.

        Args:
            api_key: API key making the request
            requested_tools: List of tools the task wants to use
            requested_agents: List of agents the task wants to use
            requested_skills: List of skills the task wants to use
            timeout: Requested timeout in seconds
            max_cost: Requested max cost per task

        Returns:
            PermissionValidation with allowed status and reason
        """
        profile = self.get_profile(api_key)

        if not profile:
            return PermissionValidation(
                allowed=False, reason="No permission profile found for API key"
            )

        # Validate tools
        if requested_tools:
            for tool in requested_tools:
                # Check if tool is in blocked list
                if tool in profile.blocked_tools:
                    return PermissionValidation(
                        allowed=False,
                        reason=f"Tool '{tool}' is explicitly blocked",
                        profile=profile,
                    )

                # Check if tool is allowed (unless wildcard)
                if "*" not in profile.allowed_tools and tool not in profile.allowed_tools:
                    return PermissionValidation(
                        allowed=False,
                        reason=f"Tool '{tool}' is not in allowed list",
                        profile=profile,
                    )

        # Validate agents
        if requested_agents:
            for agent in requested_agents:
                if "*" not in profile.allowed_agents and agent not in profile.allowed_agents:
                    return PermissionValidation(
                        allowed=False,
                        reason=f"Agent '{agent}' is not in allowed list",
                        profile=profile,
                    )

        # Validate skills
        if requested_skills:
            for skill in requested_skills:
                if "*" not in profile.allowed_skills and skill not in profile.allowed_skills:
                    return PermissionValidation(
                        allowed=False,
                        reason=f"Skill '{skill}' is not in allowed list",
                        profile=profile,
                    )

        # Validate timeout
        if timeout is not None and timeout > profile.max_execution_seconds:
            return PermissionValidation(
                allowed=False,
                reason=f"Requested timeout ({timeout}s) exceeds limit ({profile.max_execution_seconds}s)",
                profile=profile,
            )

        # Validate cost
        if max_cost is not None and max_cost > profile.max_cost_per_task:
            return PermissionValidation(
                allowed=False,
                reason=f"Requested max cost (${max_cost}) exceeds limit (${profile.max_cost_per_task})",
                profile=profile,
            )

        # All validations passed
        return PermissionValidation(
            allowed=True, reason="All permission checks passed", profile=profile
        )

    def delete_profile(self, api_key: str):
        """Delete permission profile for an API key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_key_permissions WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
