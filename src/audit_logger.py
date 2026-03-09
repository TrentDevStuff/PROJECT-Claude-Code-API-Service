"""Comprehensive audit trail logging for agentic task execution."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Logs and tracks all events in agentic task execution.

    Provides event logging (tool calls, file access, bash commands, agent spawns,
    skill invocations), security alerts, and analytics queries with SQLite
    persistence.
    """

    def __init__(self, db_path: str = "budgets.db"):
        """
        Initialize AuditLogger.

        Args:
            db_path: Path to SQLite database file (shared with BudgetManager)
        """
        self.db_path = db_path
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure audit_log table exists."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Create audit_log table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """
            )

            # Create indexes for faster queries
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_task_id
                ON audit_log(task_id)
            """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_api_key
                ON audit_log(api_key)
            """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_event_type
                ON audit_log(event_type)
            """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp)
            """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_severity
                ON audit_log(severity)
            """
            )

            await db.commit()
            self._initialized = True

    async def _log(
        self,
        event_type: str,
        task_id: str,
        api_key: str,
        details: dict[str, Any],
        severity: str = "info",
    ) -> None:
        """
        Log an event to the audit trail.

        Args:
            event_type: Type of event (tool_call, file_access, bash_command, etc.)
            task_id: ID of the task generating the event
            api_key: API key associated with the task
            details: Event details as JSON-serializable dictionary
            severity: Severity level (info, warning, critical)
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO audit_log
                (task_id, api_key, event_type, details, severity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, api_key, event_type, json.dumps(details), severity),
            )
            await db.commit()

    async def log_tool_call(
        self, task_id: str, api_key: str, tool: str, args: dict[str, Any]
    ) -> None:
        """Log a tool call event."""
        await self._log("tool_call", task_id, api_key, {"tool": tool, "args": args}, "info")

    async def log_file_access(
        self, task_id: str, api_key: str, file_path: str, access_type: str
    ) -> None:
        """Log a file access event."""
        await self._log(
            "file_access",
            task_id,
            api_key,
            {"file_path": file_path, "access_type": access_type},
            "info",
        )

    async def log_bash_command(self, task_id: str, api_key: str, command: str) -> None:
        """Log a bash command execution event."""
        await self._log("bash_command", task_id, api_key, {"command": command}, "info")

    async def log_agent_spawn(self, task_id: str, api_key: str, agent: str) -> None:
        """Log an agent spawn event."""
        await self._log("agent_spawn", task_id, api_key, {"agent": agent}, "info")

    async def log_skill_invoke(
        self, task_id: str, api_key: str, skill: str, params: dict[str, Any]
    ) -> None:
        """Log a skill invocation event."""
        await self._log(
            "skill_invoke", task_id, api_key, {"skill": skill, "params": params}, "info"
        )

    async def log_security_event(
        self, task_id: str, api_key: str, event: str, details: dict[str, Any]
    ) -> None:
        """
        Log a security event and send alert for critical events.

        Args:
            task_id: ID of the task generating the event
            api_key: API key associated with the task
            event: Type of security event (blocked_command, unauthorized_access, etc.)
            details: Event details
        """
        await self._log("security_event", task_id, api_key, {"event": event, **details}, "critical")

        # Send alert for critical security events
        if event in ["blocked_command", "unauthorized_access", "permission_violation"]:
            await self._send_security_alert(task_id, api_key, event, details)

    async def _send_security_alert(
        self, task_id: str, api_key: str, event: str, details: dict[str, Any]
    ) -> None:
        """
        Send alert for security events.

        Currently logs to console. TODO: Add email/Slack integration later.

        Args:
            task_id: ID of the task generating the event
            api_key: API key associated with the task
            event: Type of security event
            details: Event details
        """
        logger.critical(
            "SECURITY ALERT: %s - Task: %s, API Key: %s",
            event,
            task_id,
            api_key,
            extra={"detail": str(details)},
        )

    async def query_logs(
        self, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        Query audit logs with optional filters.

        Args:
            filters: Optional filters (task_id, api_key, event_type, severity, date_range)
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of audit log entries matching the filters
        """
        await self._ensure_initialized()

        # Build WHERE clause from filters
        where_clauses = []
        params = []

        if filters:
            if "task_id" in filters:
                where_clauses.append("task_id = ?")
                params.append(filters["task_id"])
            if "api_key" in filters:
                where_clauses.append("api_key = ?")
                params.append(filters["api_key"])
            if "event_type" in filters:
                where_clauses.append("event_type = ?")
                params.append(filters["event_type"])
            if "severity" in filters:
                where_clauses.append("severity = ?")
                params.append(filters["severity"])
            if "date_range" in filters:
                start_date, end_date = filters["date_range"]
                where_clauses.append("timestamp BETWEEN ? AND ?")
                params.extend([start_date, end_date])

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT id, task_id, api_key, timestamp, event_type, details, severity
                FROM audit_log
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_most_used_tools(self, days: int = 7) -> dict[str, int]:
        """
        Get the most used tools in the last N days.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping tool names to usage counts
        """
        await self._ensure_initialized()

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT details, COUNT(*) as count
                FROM audit_log
                WHERE event_type = 'tool_call' AND timestamp > ?
                GROUP BY details
                ORDER BY count DESC
                """,
                (cutoff_date,),
            )
            rows = await cursor.fetchall()

            tools_count = {}
            for row in rows:
                try:
                    details = json.loads(row[0])
                    tool = details.get("tool", "unknown")
                    tools_count[tool] = row[1]
                except json.JSONDecodeError:
                    continue

            return tools_count

    async def get_security_events_by_key(self, days: int = 7) -> dict[str, int]:
        """
        Get security events grouped by API key in the last N days.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping API keys to security event counts
        """
        await self._ensure_initialized()

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT api_key, COUNT(*) as count
                FROM audit_log
                WHERE event_type = 'security_event' AND timestamp > ?
                GROUP BY api_key
                ORDER BY count DESC
                """,
                (cutoff_date,),
            )
            rows = await cursor.fetchall()

            return {row[0]: row[1] for row in rows}

    async def get_avg_task_duration(self, days: int = 7) -> float:
        """
        Calculate average task execution time in the last N days.

        Args:
            days: Number of days to look back

        Returns:
            Average duration in seconds (calculated from first/last log timestamps per task)
        """
        await self._ensure_initialized()

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT task_id, MIN(timestamp) as start_time, MAX(timestamp) as end_time
                FROM audit_log
                WHERE timestamp > ?
                GROUP BY task_id
                """,
                (cutoff_date,),
            )
            rows = await cursor.fetchall()

            if not rows:
                return 0.0

            total_duration = 0.0
            for row in rows:
                start = datetime.fromisoformat(row[1])
                end = datetime.fromisoformat(row[2])
                duration = (end - start).total_seconds()
                total_duration += duration

            return total_duration / len(rows)
