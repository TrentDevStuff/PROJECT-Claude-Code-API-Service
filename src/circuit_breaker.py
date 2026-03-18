"""
Circuit breaker for upstream API protection.

Prevents cascade failures when the upstream Anthropic API is experiencing
persistent errors. Tracks consecutive failures and trips open after a
threshold, fast-failing requests until recovery is detected.

States:
    CLOSED (normal) -> OPEN (tripped) -> HALF_OPEN (probing)
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

RETRYABLE_CATEGORIES = frozenset(
    {"rate_limited", "overloaded", "upstream_error", "timeout", "connection_error"}
)


class CircuitBreaker:
    """
    Thread-safe circuit breaker for upstream API calls.

    Only retryable error categories count toward tripping the breaker.
    Non-retryable errors (auth_error, bad_request) pass through without
    affecting circuit state.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._state = "closed"
        self._opened_at: float | None = None

    def allow_request(self) -> bool:
        """Returns True if the circuit allows a request through."""
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                # Check if recovery timeout has elapsed
                if self._opened_at and (time.monotonic() - self._opened_at) >= self.recovery_timeout:
                    self._state = "half_open"
                    logger.info(
                        "Circuit breaker %s half-open, allowing probe request", self.name
                    )
                    return True
                return False
            # half_open — allow one probe request
            return True

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == "half_open":
                logger.info("Circuit breaker %s closing after successful probe", self.name)
            self._consecutive_failures = 0
            self._state = "closed"
            self._opened_at = None

    def record_failure(self, error_category: str | None = None) -> None:
        """Record a failed call. Only retryable categories count toward tripping."""
        if error_category and error_category not in RETRYABLE_CATEGORIES:
            return

        with self._lock:
            self._consecutive_failures += 1

            if self._state == "half_open":
                # Probe failed — reopen
                self._state = "open"
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker %s re-opened after failed probe", self.name
                )
            elif self._consecutive_failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker %s tripped open after %d consecutive failures",
                    self.name,
                    self._consecutive_failures,
                )

    @property
    def state(self) -> str:
        """Current state: 'closed', 'open', 'half_open'."""
        with self._lock:
            # Check for automatic transition to half_open
            if self._state == "open" and self._opened_at:
                if (time.monotonic() - self._opened_at) >= self.recovery_timeout:
                    return "half_open"
            return self._state

    def status(self) -> dict:
        """Health check data for /health endpoint."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_seconds": self.recovery_timeout,
            }
