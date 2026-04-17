"""Tests for circuit breaker."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from src.circuit_breaker import CircuitBreaker, RETRYABLE_CATEGORIES


def _run_with_timeout(fn, timeout_seconds: float = 2.0):
    """Run ``fn`` in a daemon thread and raise if it doesn't finish in time.

    Used to guard tests against lock-reentrancy regressions that would
    otherwise hang pytest indefinitely.
    """
    result: dict = {}

    def runner():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout_seconds)
    if t.is_alive():
        raise AssertionError(
            f"Call did not complete within {timeout_seconds}s — likely deadlock"
        )
    if "error" in result:
        raise result["error"]
    return result.get("value")


class TestCircuitBreaker:
    """Circuit breaker state machine tests."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_success_keeps_closed(self):
        cb = CircuitBreaker(name="test")
        cb.record_success()
        cb.record_success()
        assert cb.state == "closed"

    def test_failures_trip_circuit(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        cb.record_failure("rate_limited")
        cb.record_failure("rate_limited")
        assert cb.state == "closed"
        cb.record_failure("rate_limited")
        assert cb.state == "open"

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, name="test")
        cb.record_failure("timeout")
        cb.record_failure("timeout")
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_recovery_timeout_half_opens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, name="test")
        cb.record_failure("upstream_error")
        assert cb.state == "open"
        time.sleep(0.06)
        assert cb.state == "half_open"
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, name="test")
        cb.record_failure("upstream_error")
        time.sleep(0.02)
        cb.allow_request()  # transitions to half_open
        cb.record_success()
        assert cb.state == "closed"

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, name="test")
        cb.record_failure("upstream_error")
        time.sleep(0.02)
        cb.allow_request()  # transitions to half_open
        cb.record_failure("upstream_error")
        assert cb.state == "open"

    def test_non_retryable_errors_dont_trip(self):
        cb = CircuitBreaker(failure_threshold=2, name="test")
        # These should NOT count
        cb.record_failure("auth_error")
        cb.record_failure("bad_request")
        cb.record_failure("auth_error")
        cb.record_failure("bad_request")
        assert cb.state == "closed"

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        cb.record_failure("rate_limited")
        cb.record_failure("rate_limited")
        cb.record_success()  # resets
        cb.record_failure("rate_limited")
        cb.record_failure("rate_limited")
        # Only 2 consecutive, not 3
        assert cb.state == "closed"

    def test_thread_safety(self):
        cb = CircuitBreaker(failure_threshold=100, name="test")
        errors = []

        def fail_many():
            try:
                for _ in range(50):
                    cb.record_failure("timeout")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Should have tripped (200 failures, threshold 100)
        assert cb.state == "open"

    def test_status_output(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, name="sdk")
        status = _run_with_timeout(cb.status)
        assert status["name"] == "sdk"
        assert status["state"] == "closed"
        assert status["consecutive_failures"] == 0
        assert status["failure_threshold"] == 5
        assert status["recovery_timeout_seconds"] == 30.0

    def test_status_does_not_deadlock_on_non_reentrant_lock(self):
        """Regression: ``status()`` must not re-acquire ``self._lock``.

        The bug: ``status()`` took ``self._lock`` and then read ``self.state``,
        which is a ``@property`` that also takes ``self._lock``. Because
        ``threading.Lock`` is non-reentrant, this deadlocked the calling thread
        permanently. The first caller was ``/health``, which blocked the
        uvicorn single-threaded event loop and made every subsequent request
        hang. See commit fixing circuit_breaker.py for details.
        """
        cb = CircuitBreaker(name="regression")
        _run_with_timeout(cb.status, timeout_seconds=1.0)

    def test_status_reports_half_open_after_recovery_timeout(self):
        """``status()`` must compute the open→half_open transition just like
        the ``state`` property, so /health reflects reality."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, name="recovery")
        cb.record_failure("upstream_error")
        assert _run_with_timeout(cb.status)["state"] == "open"
        time.sleep(0.02)
        assert _run_with_timeout(cb.status)["state"] == "half_open"

    def test_status_is_consistent_under_concurrent_mutation(self):
        """``status()`` must return a consistent snapshot even while another
        thread is recording failures. Thread-safety regression guard."""
        cb = CircuitBreaker(failure_threshold=1000, name="concurrent")
        stop = threading.Event()

        def churn():
            while not stop.is_set():
                cb.record_failure("timeout")
                cb.record_success()

        workers = [threading.Thread(target=churn, daemon=True) for _ in range(4)]
        for w in workers:
            w.start()
        try:
            for _ in range(200):
                snap = _run_with_timeout(cb.status, timeout_seconds=1.0)
                # state must always be one of the valid values
                assert snap["state"] in ("closed", "open", "half_open")
                # counter must be non-negative
                assert snap["consecutive_failures"] >= 0
        finally:
            stop.set()
            for w in workers:
                w.join(timeout=1.0)

    def test_configurable_thresholds(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, name="custom")
        cb.record_failure("overloaded")
        assert cb.state == "open"

    def test_retryable_categories_constant(self):
        """Verify the retryable categories set is correct."""
        assert "rate_limited" in RETRYABLE_CATEGORIES
        assert "overloaded" in RETRYABLE_CATEGORIES
        assert "upstream_error" in RETRYABLE_CATEGORIES
        assert "timeout" in RETRYABLE_CATEGORIES
        assert "connection_error" in RETRYABLE_CATEGORIES
        assert "auth_error" not in RETRYABLE_CATEGORIES
        assert "bad_request" not in RETRYABLE_CATEGORIES
