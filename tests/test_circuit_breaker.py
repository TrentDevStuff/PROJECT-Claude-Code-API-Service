"""Tests for circuit breaker."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from src.circuit_breaker import CircuitBreaker, RETRYABLE_CATEGORIES


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
        status = cb.status()
        assert status["name"] == "sdk"
        assert status["state"] == "closed"
        assert status["consecutive_failures"] == 0
        assert status["failure_threshold"] == 5
        assert status["recovery_timeout_seconds"] == 30.0

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
