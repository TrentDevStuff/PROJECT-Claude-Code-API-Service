"""Per-project budget tracking system for API usage monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import aiosqlite


class BudgetManager:
    """
    Manages per-project budgets and tracks API usage.

    Provides budget checking, usage tracking, and reporting capabilities
    with SQLite-based persistent storage.
    """

    def __init__(self, db_path: str = "budgets.db"):
        """
        Initialize BudgetManager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Create projects table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    monthly_token_limit INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create usage_log table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """
            )

            # Create index for faster queries
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_usage_project_timestamp
                ON usage_log(project_id, timestamp)
            """
            )

            await db.commit()

        self._initialized = True

    async def check_budget(self, project_id: str, estimated_tokens: int) -> bool:
        """
        Check if project has sufficient budget for estimated token usage.

        Args:
            project_id: Unique project identifier
            estimated_tokens: Estimated tokens needed for request

        Returns:
            True if budget allows, False if over budget
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            # Get project's monthly limit
            async with db.execute(
                "SELECT monthly_token_limit FROM projects WHERE id = ?", (project_id,)
            ) as cursor:
                row = await cursor.fetchone()

                if row is None:
                    # No budget set = unlimited
                    return True

                monthly_limit = row[0]

                if monthly_limit is None:
                    # Unlimited budget
                    return True

            # Calculate current month's usage
            start_of_month = datetime.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

            async with db.execute(
                """
                SELECT COALESCE(SUM(tokens), 0)
                FROM usage_log
                WHERE project_id = ? AND timestamp >= ?
                """,
                (project_id, start_of_month),
            ) as cursor:
                row = await cursor.fetchone()
                current_usage = row[0]

            # Check if estimated usage would exceed limit
            return (current_usage + estimated_tokens) <= monthly_limit

    async def track_usage(self, project_id: str, model: str, tokens: int, cost: float) -> None:
        """
        Record API usage for a project.

        Args:
            project_id: Unique project identifier
            model: Model name used (e.g., "haiku", "sonnet", "opus")
            tokens: Number of tokens consumed
            cost: Cost in USD
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO usage_log (project_id, model, tokens, cost_usd, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, model, tokens, cost, datetime.now()),
            )
            await db.commit()

    async def get_usage(self, project_id: str, period: str = "month") -> dict[str, Any]:
        """
        Get usage statistics for a project.

        Args:
            project_id: Unique project identifier
            period: Time period - "month", "week", or "day"

        Returns:
            Dictionary containing usage statistics:
            {
                "total_tokens": int,
                "total_cost": float,
                "by_model": {model_name: {"tokens": int, "cost": float}},
                "limit": int or None,
                "remaining": int or None
            }
        """
        await self._ensure_initialized()

        # Calculate time threshold based on period
        now = datetime.now()
        if period == "month":
            threshold = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            threshold = now - timedelta(days=7)
        elif period == "day":
            threshold = now - timedelta(days=1)
        else:
            raise ValueError(f"Invalid period: {period}. Use 'month', 'week', or 'day'")

        async with aiosqlite.connect(self.db_path) as db:
            # Get monthly limit
            async with db.execute(
                "SELECT monthly_token_limit FROM projects WHERE id = ?", (project_id,)
            ) as cursor:
                row = await cursor.fetchone()
                limit = row[0] if row else None

            # Get total usage
            async with db.execute(
                """
                SELECT
                    COALESCE(SUM(tokens), 0) as total_tokens,
                    COALESCE(SUM(cost_usd), 0.0) as total_cost
                FROM usage_log
                WHERE project_id = ? AND timestamp >= ?
                """,
                (project_id, threshold),
            ) as cursor:
                row = await cursor.fetchone()
                total_tokens = row[0]
                total_cost = row[1]

            # Get usage by model
            by_model = {}
            async with db.execute(
                """
                SELECT
                    model,
                    SUM(tokens) as tokens,
                    SUM(cost_usd) as cost
                FROM usage_log
                WHERE project_id = ? AND timestamp >= ?
                GROUP BY model
                """,
                (project_id, threshold),
            ) as cursor:
                async for row in cursor:
                    model_name = row[0]
                    by_model[model_name] = {"tokens": row[1], "cost": row[2]}

            # Calculate remaining budget
            remaining = None
            if limit is not None:
                remaining = limit - total_tokens

            return {
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "by_model": by_model,
                "limit": limit,
                "remaining": remaining,
            }

    async def set_budget(
        self, project_id: str, monthly_limit: int | None, name: str | None = None
    ) -> None:
        """
        Set or update monthly token budget for a project.

        Args:
            project_id: Unique project identifier
            monthly_limit: Monthly token limit (None for unlimited)
            name: Optional project name
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            # Check if project exists
            async with db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)) as cursor:
                exists = await cursor.fetchone() is not None

            if exists:
                # Update existing project
                if name is not None:
                    await db.execute(
                        """
                        UPDATE projects
                        SET monthly_token_limit = ?, name = ?
                        WHERE id = ?
                        """,
                        (monthly_limit, name, project_id),
                    )
                else:
                    await db.execute(
                        """
                        UPDATE projects
                        SET monthly_token_limit = ?
                        WHERE id = ?
                        """,
                        (monthly_limit, project_id),
                    )
            else:
                # Insert new project
                await db.execute(
                    """
                    INSERT INTO projects (id, name, monthly_token_limit)
                    VALUES (?, ?, ?)
                    """,
                    (project_id, name or project_id, monthly_limit),
                )

            await db.commit()
