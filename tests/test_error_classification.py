"""Tests for CLI stderr error classification and HTTP status mapping."""

from __future__ import annotations

from src.worker_pool import _classify_cli_stderr
from src.api import _ERROR_HTTP_MAP


class TestCliStderrClassification:
    """Verify CLI stderr patterns map to correct error categories."""

    def test_rate_limit_pattern(self):
        assert _classify_cli_stderr("Error: rate limit exceeded") == "rate_limited"

    def test_429_pattern(self):
        assert _classify_cli_stderr("HTTP 429 Too Many Requests") == "rate_limited"

    def test_overloaded_pattern(self):
        assert _classify_cli_stderr("API is overloaded") == "overloaded"

    def test_529_pattern(self):
        assert _classify_cli_stderr("status code: 529") == "overloaded"

    def test_timeout_pattern(self):
        assert _classify_cli_stderr("Request timed out after 30s") == "timeout"

    def test_timeout_alternate(self):
        assert _classify_cli_stderr("Connection timeout") == "timeout"

    def test_server_error_pattern(self):
        assert _classify_cli_stderr("Internal server error") == "upstream_error"

    def test_500_pattern(self):
        assert _classify_cli_stderr("HTTP 500 error") == "upstream_error"

    def test_auth_pattern(self):
        assert _classify_cli_stderr("Authentication failed") == "auth_error"

    def test_unknown_error_fallback(self):
        assert _classify_cli_stderr("Something completely unexpected") == "cli_error"

    def test_empty_stderr(self):
        assert _classify_cli_stderr("") == "cli_error"


class TestErrorHttpMap:
    """Verify error categories map to correct HTTP status codes."""

    def test_rate_limited_maps_to_429(self):
        assert _ERROR_HTTP_MAP["rate_limited"] == 429

    def test_overloaded_maps_to_503(self):
        assert _ERROR_HTTP_MAP["overloaded"] == 503

    def test_upstream_error_maps_to_502(self):
        assert _ERROR_HTTP_MAP["upstream_error"] == 502

    def test_auth_error_maps_to_502(self):
        assert _ERROR_HTTP_MAP["auth_error"] == 502

    def test_timeout_maps_to_504(self):
        assert _ERROR_HTTP_MAP["timeout"] == 504

    def test_connection_error_maps_to_502(self):
        assert _ERROR_HTTP_MAP["connection_error"] == 502

    def test_bad_request_maps_to_400(self):
        assert _ERROR_HTTP_MAP["bad_request"] == 400

    def test_cli_error_maps_to_502(self):
        assert _ERROR_HTTP_MAP["cli_error"] == 502

    def test_internal_error_maps_to_500(self):
        assert _ERROR_HTTP_MAP["internal_error"] == 500
