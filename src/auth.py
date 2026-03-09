"""
Authentication and rate limiting for Claude Code API Service.

Provides:
- API key generation and validation
- SQLite-based key storage
- Rate limiting per API key
- FastAPI dependency for Bearer token authentication
"""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ============================================================================
# Database Setup
# ============================================================================

API_KEY_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    rate_limit INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    revoked BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_project_id ON api_keys(project_id);
CREATE INDEX IF NOT EXISTS idx_revoked ON api_keys(revoked);
"""

RATE_LIMIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limits (
    api_key TEXT NOT NULL,
    window_start TIMESTAMP NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (api_key, window_start),
    FOREIGN KEY (api_key) REFERENCES api_keys(key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_window_start ON rate_limits(window_start);
"""


# ============================================================================
# AuthManager
# ============================================================================


class AuthManager:
    """
    Manages API key authentication and rate limiting.

    Features:
    - Generates cryptographically secure API keys
    - Validates keys against SQLite database
    - Enforces per-key rate limits (requests per minute)
    - Tracks key usage timestamps
    - Supports key revocation
    """

    def __init__(self, db_path: str = "data/auth.db", window_seconds: int = 60):
        """
        Initialize AuthManager.

        Args:
            db_path: Path to SQLite database file
            window_seconds: Rate limit window in seconds (default: 60 = 1 minute)
        """
        self.db_path = db_path
        self.window_seconds = window_seconds

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript(API_KEY_SCHEMA)
            conn.executescript(RATE_LIMIT_SCHEMA)

    def generate_key(self, project_id: str, rate_limit: int = 100) -> str:
        """
        Generate a new API key for a project.

        Args:
            project_id: Project identifier
            rate_limit: Maximum requests per minute (default: 100)

        Returns:
            API key string (format: cc_<40 hex chars>)
        """
        # Generate cryptographically secure random key
        random_bytes = secrets.token_bytes(20)
        api_key = f"cc_{random_bytes.hex()}"

        # Store in database
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (key, project_id, rate_limit, created_at, revoked)
                VALUES (?, ?, ?, ?, 0)
                """,
                (api_key, project_id, rate_limit, datetime.now()),
            )

        return api_key

    def validate_key(self, api_key: str) -> tuple[bool, str | None]:
        """
        Validate an API key.

        Args:
            api_key: API key to validate

        Returns:
            Tuple of (is_valid: bool, project_id: Optional[str])
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT project_id, revoked FROM api_keys
                WHERE key = ?
                """,
                (api_key,),
            )
            row = cursor.fetchone()

        if row is None:
            return False, None

        if row["revoked"]:
            return False, None

        return True, row["project_id"]

    def check_rate_limit(self, api_key: str) -> bool:
        """
        Check if API key is within rate limit.

        Args:
            api_key: API key to check

        Returns:
            True if request allowed, False if rate limit exceeded
        """
        now = datetime.now()
        window_start = now.replace(second=0, microsecond=0)

        with self._get_connection() as conn:
            # Get rate limit for this key
            cursor = conn.execute("SELECT rate_limit FROM api_keys WHERE key = ?", (api_key,))
            row = cursor.fetchone()

            if row is None:
                return False

            max_requests = row["rate_limit"]

            # Get current request count for this window
            cursor = conn.execute(
                """
                SELECT request_count FROM rate_limits
                WHERE api_key = ? AND window_start = ?
                """,
                (api_key, window_start),
            )
            limit_row = cursor.fetchone()

            if limit_row is None:
                # First request in this window
                conn.execute(
                    """
                    INSERT INTO rate_limits (api_key, window_start, request_count)
                    VALUES (?, ?, 1)
                    """,
                    (api_key, window_start),
                )
                current_count = 1
            else:
                current_count = limit_row["request_count"]

                # Check if we've exceeded the limit
                if current_count >= max_requests:
                    return False

                # Increment counter
                conn.execute(
                    """
                    UPDATE rate_limits
                    SET request_count = request_count + 1
                    WHERE api_key = ? AND window_start = ?
                    """,
                    (api_key, window_start),
                )

            # Update last_used_at
            conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = ?
                WHERE key = ?
                """,
                (now, api_key),
            )

        return True

    def revoke_key(self, api_key: str) -> bool:
        """
        Revoke an API key.

        Args:
            api_key: API key to revoke

        Returns:
            True if key was revoked, False if key not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE api_keys
                SET revoked = 1
                WHERE key = ?
                """,
                (api_key,),
            )
            return cursor.rowcount > 0

    def get_key_info(self, api_key: str) -> dict | None:
        """
        Get information about an API key.

        Args:
            api_key: API key to query

        Returns:
            Dict with key info, or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT key, project_id, rate_limit, created_at, last_used_at, revoked
                FROM api_keys
                WHERE key = ?
                """,
                (api_key,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return dict(row)

    def cleanup_old_rate_limits(self, hours: int = 24):
        """
        Clean up old rate limit records.

        Args:
            hours: Remove records older than this many hours
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM rate_limits
                WHERE window_start < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount

        return deleted


# ============================================================================
# FastAPI Dependencies
# ============================================================================

# Global auth manager instance (initialized in main.py)
auth_manager: AuthManager | None = None

# HTTP Bearer token security scheme
security = HTTPBearer()


def initialize_auth(manager: AuthManager):
    """Initialize global auth manager instance."""
    global auth_manager
    auth_manager = manager


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    FastAPI dependency for API key verification.

    Usage in endpoints:
        @app.get("/protected")
        async def protected_route(project_id: str = Depends(verify_api_key)):
            return {"project_id": project_id}

    Raises:
        HTTPException: If API key is invalid, revoked, or rate limited

    Returns:
        project_id: Project ID associated with the API key
    """
    if auth_manager is None:
        raise HTTPException(status_code=500, detail="Authentication not initialized")

    api_key = credentials.credentials

    # Validate key
    is_valid, project_id = auth_manager.validate_key(api_key)

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    # Check rate limit
    if not auth_manager.check_rate_limit(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    return project_id
