"""Tests for error tracker."""

from __future__ import annotations

import threading
import time

from src.error_tracker import ErrorTracker


class TestErrorTracker:
    """Sliding window error counter tests."""

    def test_record_and_rates(self):
        tracker = ErrorTracker(window_seconds=60.0)
        tracker.record("rate_limited", path="sdk")
        tracker.record("timeout", path="sdk")
        tracker.record("rate_limited", path="sdk")

        rates = tracker.rates()
        assert rates["sdk"]["rate_limited"] == 2
        assert rates["sdk"]["timeout"] == 1

    def test_window_expiry(self):
        tracker = ErrorTracker(window_seconds=0.05)
        tracker.record("rate_limited", path="sdk")
        assert tracker.total_errors() == 1
        time.sleep(0.06)
        assert tracker.total_errors() == 0

    def test_multiple_categories(self):
        tracker = ErrorTracker()
        tracker.record("rate_limited", path="sdk")
        tracker.record("timeout", path="sdk")
        tracker.record("overloaded", path="sdk")

        rates = tracker.rates()
        assert len(rates["sdk"]) == 3

    def test_multiple_paths(self):
        tracker = ErrorTracker()
        tracker.record("rate_limited", path="sdk")
        tracker.record("cli_error", path="cli")

        rates = tracker.rates()
        assert "sdk" in rates
        assert "cli" in rates
        assert rates["sdk"]["rate_limited"] == 1
        assert rates["cli"]["cli_error"] == 1

    def test_total_errors(self):
        tracker = ErrorTracker()
        tracker.record("rate_limited", path="sdk")
        tracker.record("timeout", path="cli")
        tracker.record("overloaded", path="sdk")
        assert tracker.total_errors() == 3

    def test_summary_format(self):
        tracker = ErrorTracker(window_seconds=300.0)
        tracker.record("rate_limited", path="sdk")

        summary = tracker.summary()
        assert summary["window_seconds"] == 300.0
        assert summary["total_errors"] == 1
        assert "by_path" in summary
        assert summary["by_path"]["sdk"]["rate_limited"] == 1

    def test_thread_safety(self):
        tracker = ErrorTracker()
        errors = []

        def record_many():
            try:
                for _ in range(100):
                    tracker.record("timeout", path="sdk")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert tracker.total_errors() == 400

    def test_empty_tracker(self):
        tracker = ErrorTracker()
        assert tracker.rates() == {}
        assert tracker.total_errors() == 0
        summary = tracker.summary()
        assert summary["total_errors"] == 0
        assert summary["by_path"] == {}
