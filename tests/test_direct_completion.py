"""Tests for direct completion error classification."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic

from src.direct_completion import DirectCompletionClient
from src.worker_pool import TaskStatus


class TestDirectCompletionErrorClassification:
    """Verify each Anthropic SDK error type maps to correct error_category."""

    def _make_client(self):
        """Create client with mocked Anthropic SDK."""
        with patch("src.direct_completion.anthropic.Anthropic"):
            client = DirectCompletionClient()
        return client

    def _call(self, client, exc):
        """Call complete() with a mocked exception."""
        client.client.messages.create.side_effect = exc
        return client.complete(
            messages=[{"role": "user", "content": "test"}],
            model="sonnet",
        )

    def test_rate_limit_error_classification(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {"retry-after": "5"}
        exc = anthropic.RateLimitError(
            message="rate limited", response=mock_response, body=None
        )
        result = self._call(client, exc)

        assert result.status == TaskStatus.FAILED
        assert result.error_category == "rate_limited"
        assert result.upstream_status == 429

    def test_rate_limit_retry_after_extraction(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {"retry-after": "12.5"}
        exc = anthropic.RateLimitError(
            message="rate limited", response=mock_response, body=None
        )
        result = self._call(client, exc)

        assert result.retry_after == 12.5

    def test_overloaded_529_classification(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {}
        exc = anthropic.InternalServerError(
            message="overloaded", response=mock_response, body=None
        )
        exc.status_code = 529
        result = self._call(client, exc)

        assert result.error_category == "overloaded"
        assert result.upstream_status == 529

    def test_server_error_500_classification(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {}
        exc = anthropic.InternalServerError(
            message="internal error", response=mock_response, body=None
        )
        exc.status_code = 500
        result = self._call(client, exc)

        assert result.error_category == "upstream_error"
        assert result.upstream_status == 500

    def test_timeout_error_classification(self):
        client = self._make_client()
        exc = anthropic.APITimeoutError(request=MagicMock())
        result = self._call(client, exc)

        assert result.error_category == "timeout"
        assert result.upstream_status is None

    def test_connection_error_classification(self):
        client = self._make_client()
        exc = anthropic.APIConnectionError(request=MagicMock())
        result = self._call(client, exc)

        assert result.error_category == "connection_error"

    def test_auth_error_classification(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {}
        exc = anthropic.AuthenticationError(
            message="unauthorized", response=mock_response, body=None
        )
        result = self._call(client, exc)

        assert result.error_category == "auth_error"
        assert result.upstream_status == 401

    def test_bad_request_classification(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {}
        exc = anthropic.BadRequestError(
            message="invalid", response=mock_response, body=None
        )
        result = self._call(client, exc)

        assert result.error_category == "bad_request"
        assert result.upstream_status == 400

    def test_generic_api_error_fallback(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.headers = {}
        exc = anthropic.APIError(
            message="unknown api error", request=MagicMock(), body=None
        )
        result = self._call(client, exc)

        assert result.error_category == "upstream_error"

    def test_non_api_exception(self):
        client = self._make_client()
        result = self._call(client, RuntimeError("unexpected"))

        assert result.error_category == "internal_error"
