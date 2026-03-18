"""
Sliding window error rate tracker.

Tracks error occurrences by category and execution path (sdk/cli)
within a configurable time window. Provides aggregated counts for
the /health endpoint and operational awareness.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class _ErrorEntry:
    """Single error occurrence."""

    timestamp: float
    category: str
    path: str


class ErrorTracker:
    """
    Thread-safe sliding window error counter.

    Records error occurrences and provides counts within a configurable
    time window (default 5 minutes). Old entries are pruned on read.
    """

    def __init__(self, window_seconds: float = 300.0):
        self.window_seconds = window_seconds
        self._entries: deque[_ErrorEntry] = deque()
        self._lock = threading.Lock()

    def record(self, category: str, path: str = "sdk") -> None:
        """Record an error occurrence."""
        entry = _ErrorEntry(
            timestamp=time.monotonic(),
            category=category,
            path=path,
        )
        with self._lock:
            self._entries.append(entry)

    def _prune(self) -> None:
        """Remove entries older than the window. Caller must hold lock."""
        cutoff = time.monotonic() - self.window_seconds
        while self._entries and self._entries[0].timestamp < cutoff:
            self._entries.popleft()

    def rates(self) -> dict[str, dict[str, int]]:
        """
        Return error counts by path and category within the window.

        Returns:
            {"sdk": {"rate_limited": 3, "timeout": 1}, "cli": {"cli_error": 2}}
        """
        with self._lock:
            self._prune()
            result: dict[str, dict[str, int]] = {}
            for entry in self._entries:
                path_counts = result.setdefault(entry.path, {})
                path_counts[entry.category] = path_counts.get(entry.category, 0) + 1
            return result

    def total_errors(self) -> int:
        """Total errors in current window."""
        with self._lock:
            self._prune()
            return len(self._entries)

    def summary(self) -> dict:
        """Summary dict for health endpoint."""
        rates = self.rates()
        total = sum(sum(cats.values()) for cats in rates.values())
        return {
            "window_seconds": self.window_seconds,
            "total_errors": total,
            "by_path": rates,
        }
