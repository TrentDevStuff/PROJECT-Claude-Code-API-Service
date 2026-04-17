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


class TestPromptCaching:
    """Verify cache_control markers are placed correctly and cost accounting
    honors Anthropic's read/write multipliers.

    These tests use the _apply_cache_markers helper directly because it is
    pure (no SDK dependency) and lets us assert on the exact request shape.
    The end-to-end path is covered by test_complete_sends_cache_markers below.
    """

    def test_marker_on_last_system_block_string_form(self):
        kwargs = {
            "messages": [{"role": "user", "content": "hi"}],
            "system": "You are a helpful assistant.",
            "tools": [{"name": "search", "description": "x", "input_schema": {"type": "object"}}],
        }
        count = DirectCompletionClient._apply_cache_markers(kwargs)

        # System string → list of blocks with cache_control on the last block.
        # That single marker caches tools + system together (render order is
        # tools → system → messages).
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
        # Tools themselves are not individually marked when system is present.
        assert "cache_control" not in kwargs["tools"][-1]
        # Last user message (string) → promoted to blocks with cache_control.
        user_msg_content = kwargs["messages"][-1]["content"]
        assert isinstance(user_msg_content, list)
        assert user_msg_content[-1]["cache_control"] == {"type": "ephemeral"}
        assert count == 2

    def test_marker_on_last_tool_when_no_system(self):
        kwargs = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "tools": [
                {"name": "a", "description": "x", "input_schema": {"type": "object"}},
                {"name": "b", "description": "y", "input_schema": {"type": "object"}},
            ],
        }
        count = DirectCompletionClient._apply_cache_markers(kwargs)

        # With no system prompt, cache the tools prefix by marking the last tool.
        assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in kwargs["tools"][0]
        # Last user message content (list form) → marker on the last block.
        assert kwargs["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        assert count == 2

    def test_no_markers_when_nothing_cacheable(self):
        kwargs = {"messages": [{"role": "assistant", "content": "foo"}]}
        count = DirectCompletionClient._apply_cache_markers(kwargs)
        # No system, no tools, no user message — nothing to cache.
        assert count == 0
        assert "system" not in kwargs
        assert "tools" not in kwargs

    def test_marker_placed_on_last_user_message_not_earlier(self):
        """Marker must sit on the LAST user turn so follow-up requests (which
        append new assistant+user turns) read the prior history from cache."""
        kwargs = {
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "response"},
                {"role": "user", "content": "second"},
            ],
        }
        DirectCompletionClient._apply_cache_markers(kwargs)

        # First user message unchanged (still a string).
        assert kwargs["messages"][0]["content"] == "first"
        # Last user message promoted to blocks with cache_control.
        assert isinstance(kwargs["messages"][-1]["content"], list)
        assert kwargs["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_respects_existing_list_form_system(self):
        kwargs = {
            "messages": [{"role": "user", "content": "hi"}],
            "system": [
                {"type": "text", "text": "block 1"},
                {"type": "text", "text": "block 2"},
            ],
        }
        DirectCompletionClient._apply_cache_markers(kwargs)

        # Only the LAST system block gets marked; earlier blocks untouched.
        assert "cache_control" not in kwargs["system"][0]
        assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}


class TestCompleteSendsCacheMarkers:
    """Integration: complete() with caching enabled annotates the outgoing
    Messages API request and correctly accounts for cache read/write costs."""

    def _mock_response(self, input_tokens=10, output_tokens=20,
                       cache_creation=0, cache_read=0):
        resp = MagicMock()
        resp.usage.input_tokens = input_tokens
        resp.usage.output_tokens = output_tokens
        resp.usage.cache_creation_input_tokens = cache_creation
        resp.usage.cache_read_input_tokens = cache_read
        resp.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "hi"
        resp.content = [text_block]
        return resp

    def test_cache_markers_sent_when_enabled(self):
        with patch("src.direct_completion.anthropic.Anthropic"), \
             patch("src.direct_completion.settings") as mock_settings:
            mock_settings.prompt_caching_enabled = True
            mock_settings.sdk_max_retries = 2
            mock_settings.sdk_timeout_seconds = 60.0
            client = DirectCompletionClient()
            client.client.messages.create.return_value = self._mock_response()

            client.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="sonnet",
                system="You are helpful.",
                tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
            )

            sent = client.client.messages.create.call_args.kwargs
            assert isinstance(sent["system"], list)
            assert sent["system"][-1]["cache_control"] == {"type": "ephemeral"}
            assert sent["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_cache_markers_omitted_when_disabled(self):
        with patch("src.direct_completion.anthropic.Anthropic"), \
             patch("src.direct_completion.settings") as mock_settings:
            mock_settings.prompt_caching_enabled = False
            mock_settings.sdk_max_retries = 2
            mock_settings.sdk_timeout_seconds = 60.0
            client = DirectCompletionClient()
            client.client.messages.create.return_value = self._mock_response()

            client.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="sonnet",
                system="You are helpful.",
                tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
            )

            sent = client.client.messages.create.call_args.kwargs
            # System stays as plain string; no cache_control inserted anywhere.
            assert sent["system"] == "You are helpful."
            assert "cache_control" not in sent["tools"][-1]
            assert sent["messages"][-1]["content"] == "hello"

    def test_cost_uses_read_and_write_multipliers(self):
        """Cache writes bill at 1.25× input rate, reads at 0.1×. Uncached
        input + output bill at base rates. Verify the sum matches exactly."""
        with patch("src.direct_completion.anthropic.Anthropic"), \
             patch("src.direct_completion.settings") as mock_settings:
            mock_settings.prompt_caching_enabled = True
            mock_settings.sdk_max_retries = 2
            mock_settings.sdk_timeout_seconds = 60.0
            client = DirectCompletionClient()
            # Sonnet rates: $3/M input, $15/M output.
            client.client.messages.create.return_value = self._mock_response(
                input_tokens=1_000_000,
                output_tokens=0,
                cache_creation=1_000_000,
                cache_read=1_000_000,
            )

            result = client.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="sonnet",
                system="stable system prompt",
            )

            # Expected cost:
            #   1M uncached input  @ $3.00       = $3.00
            #   1M cache write     @ $3.00 × 1.25 = $3.75
            #   1M cache read      @ $3.00 × 0.10 = $0.30
            #   0  output                          = $0.00
            #   Total                              = $7.05
            assert result.cost == 7.05
