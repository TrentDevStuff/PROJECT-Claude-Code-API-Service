"""
Phase 1 tests: Tool Calling Passthrough — Core Support.

Tests cover:
- TaskResult backward compatibility and new fields
- DirectCompletionClient tool passing and response extraction
- AIServiceResponse content_blocks field
- convert_response stop_reason handling
- convert_to_messages tool field preservation
- Feature flag gating in /v1/process
- Tool validation warnings and audit logging
- Contract tests for response shapes
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.compatibility_adapter import (
    AIServiceResponse,
    Message,
    MessageRole,
    ProcessRequest,
    convert_response,
    convert_to_messages,
)
from src.worker_pool import TaskResult, TaskStatus


# ============================================================================
# TaskResult Tests (worker_pool.py)
# ============================================================================


class TestTaskResultBackwardCompat:
    """Verify existing code that reads .completion still works."""

    def test_task_result_backward_compat(self):
        """Existing code that reads .completion still works."""
        r = TaskResult(task_id="t1", status=TaskStatus.COMPLETED, completion="hello")
        assert isinstance(r.completion, str)
        assert r.content_blocks is None
        assert r.stop_reason is None

    def test_task_result_tool_use_fields(self):
        """New tool-aware code uses content_blocks and stop_reason."""
        blocks = [
            {"type": "tool_use", "id": "toolu_abc", "name": "search", "input": {"q": "test"}}
        ]
        r = TaskResult(
            task_id="t1",
            status=TaskStatus.COMPLETED,
            content_blocks=blocks,
            stop_reason="tool_use",
        )
        assert r.content_blocks is not None
        assert r.stop_reason == "tool_use"
        assert r.completion is None


# ============================================================================
# DirectCompletionClient Tests (direct_completion.py)
# ============================================================================


class TestDirectCompletionTools:
    """Test tool calling support in DirectCompletionClient."""

    def _make_client(self):
        """Create client with mocked Anthropic SDK."""
        with patch("src.direct_completion.anthropic.Anthropic"):
            client = __import__("src.direct_completion", fromlist=["DirectCompletionClient"]).DirectCompletionClient()
        return client

    def _mock_text_response(self):
        """Create a mock text-only Anthropic response."""
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Hello world"
        mock_block.id = None
        mock_block.name = None
        mock_block.input = None

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        return mock_response

    def _mock_tool_use_response(self):
        """Create a mock tool_use Anthropic response."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I'll search for that."
        text_block.id = None
        text_block.name = None
        text_block.input = None

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "search"
        tool_block.input = {"q": "test"}
        tool_block.text = None  # no text attr check
        del tool_block.text  # hasattr(block, "text") should be False

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.stop_reason = "tool_use"
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 15
        return mock_response

    def test_complete_with_tools(self):
        """Tools and tool_choice are passed to anthropic.messages.create()."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_text_response()

        tools = [{"name": "search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}]
        tool_choice = {"type": "auto"}

        result = client.complete(
            messages=[{"role": "user", "content": "test"}],
            model="sonnet",
            tools=tools,
            tool_choice=tool_choice,
        )

        call_kwargs = client.client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] == tools
        assert "tool_choice" in call_kwargs
        assert call_kwargs["tool_choice"] == tool_choice
        assert result.status == TaskStatus.COMPLETED

    def test_tool_use_response_extraction(self):
        """tool_use blocks are extracted to content_blocks, completion is text summary."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_tool_use_response()

        tools = [{"name": "search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}]
        result = client.complete(
            messages=[{"role": "user", "content": "search for test"}],
            model="sonnet",
            tools=tools,
        )

        assert result.status == TaskStatus.COMPLETED
        assert result.content_blocks is not None
        assert len(result.content_blocks) == 2
        assert result.content_blocks[0]["type"] == "text"
        assert result.content_blocks[1]["type"] == "tool_use"
        assert result.content_blocks[1]["name"] == "search"
        assert result.content_blocks[1]["id"] == "toolu_123"
        assert result.content_blocks[1]["input"] == {"q": "test"}
        assert result.stop_reason == "tool_use"
        assert result.completion == "I'll search for that."

    def test_text_response_no_content_blocks(self):
        """Text-only response does not set content_blocks."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_text_response()

        result = client.complete(
            messages=[{"role": "user", "content": "hello"}],
            model="sonnet",
        )

        assert result.status == TaskStatus.COMPLETED
        assert result.content_blocks is None
        assert result.stop_reason == "end_turn"
        assert result.completion == "Hello world"

    def test_structured_messages_preserved(self):
        """Messages with list content pass through unchanged to API."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_text_response()

        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_123", "content": "result data"}
            ]},
        ]
        result = client.complete(messages=messages, model="sonnet")

        call_kwargs = client.client.messages.create.call_args[1]
        # The structured content should pass through
        assert call_kwargs["messages"][0]["content"] == messages[0]["content"]

    def test_tool_schema_validation_warnings(self):
        """Missing name/description logged as warning."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_text_response()

        tools = [
            {"description": "No name", "input_schema": {"type": "object"}},
            {"name": "no_desc", "input_schema": {"type": "object"}},
            {"name": "bad_schema", "description": "Bad", "input_schema": {"type": "array"}},
        ]

        with patch("src.direct_completion.logger") as mock_logger:
            client.complete(
                messages=[{"role": "user", "content": "test"}],
                model="sonnet",
                tools=tools,
            )
            # Should have warning calls for each validation issue
            warning_calls = [c for c in mock_logger.warning.call_args_list if "tool_validation_warning" in str(c)]
            assert len(warning_calls) == 3

    def test_tool_call_audit_log(self):
        """Tool calls produce structured log entries."""
        client = self._make_client()
        client.client.messages.create.return_value = self._mock_tool_use_response()

        tools = [{"name": "search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}]

        with patch("src.direct_completion.logger") as mock_logger:
            client.complete(
                messages=[{"role": "user", "content": "test"}],
                model="sonnet",
                tools=tools,
            )
            # Should have audit log for tool call
            info_calls = mock_logger.info.call_args_list
            audit_calls = [c for c in info_calls if "tool_call_passthrough" in str(c)]
            assert len(audit_calls) >= 1


# ============================================================================
# Compatibility Adapter Tests (compatibility_adapter.py)
# ============================================================================


class TestAIServiceResponseContentBlocks:
    """Test content_blocks field in AIServiceResponse."""

    def test_content_blocks_populated(self):
        """content_blocks field populated, content has text summary."""
        blocks = [
            {"type": "text", "text": "I'll search."},
            {"type": "tool_use", "id": "toolu_123", "name": "search", "input": {"q": "test"}},
        ]
        response = AIServiceResponse(
            content="I'll search.",
            content_blocks=blocks,
            model="claude-sonnet-4-5",
            provider="anthropic",
            metadata={"finish_reason": "tool_use", "usage": {}},
        )
        data = response.model_dump()
        assert isinstance(data["content"], str)
        assert len(data["content_blocks"]) == 2
        assert data["content_blocks"][1]["type"] == "tool_use"

    def test_content_blocks_none_for_text(self):
        """content_blocks is None for text-only responses."""
        response = AIServiceResponse(
            content="Hello",
            model="claude-sonnet-4-5",
            provider="anthropic",
            metadata={"finish_reason": "stop", "usage": {}},
        )
        data = response.model_dump()
        assert data["content_blocks"] is None
        assert isinstance(data["content"], str)


class TestConvertResponse:
    """Test convert_response handles stop_reason and content_blocks."""

    def test_convert_response_stop_reason(self):
        """stop_reason flows to metadata.finish_reason."""
        response = convert_response(
            claude_response={"content": "hello", "stop_reason": "end_turn", "usage": {}, "cost": 0},
            original_provider="anthropic",
            original_model="sonnet",
            claude_model="sonnet",
        )
        assert response.metadata["finish_reason"] == "end_turn"

    def test_convert_response_tool_use(self):
        """List content produces content_blocks and text summary."""
        blocks = [
            {"type": "text", "text": "Searching."},
            {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {}},
        ]
        response = convert_response(
            claude_response={"content": blocks, "stop_reason": "tool_use", "usage": {}, "cost": 0},
            original_provider="anthropic",
            original_model="sonnet",
            claude_model="sonnet",
        )
        assert response.content_blocks is not None
        assert len(response.content_blocks) == 2
        assert response.content == "Searching."
        assert response.metadata["finish_reason"] == "tool_use"


class TestConvertToMessages:
    """Test convert_to_messages preserves tool fields."""

    def test_preserves_tool_calls(self):
        """tool_calls field preserved in message conversion."""
        request = ProcessRequest(
            provider="anthropic",
            model_name="sonnet",
            messages=[
                Message(
                    role=MessageRole.ASSISTANT,
                    content="I'll help.",
                    tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
                ),
            ],
        )
        result = convert_to_messages(request)
        assert result[0]["tool_calls"] is not None
        assert len(result[0]["tool_calls"]) == 1

    def test_preserves_tool_call_id(self):
        """tool_call_id field preserved in message conversion."""
        request = ProcessRequest(
            provider="anthropic",
            model_name="sonnet",
            messages=[
                Message(
                    role=MessageRole.TOOL,
                    content="result data",
                    tool_call_id="call_1",
                ),
            ],
        )
        result = convert_to_messages(request)
        assert result[0]["tool_call_id"] == "call_1"

    def test_preserves_structured_content(self):
        """Structured content (list) in messages preserved."""
        request = ProcessRequest(
            provider="anthropic",
            model_name="sonnet",
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=[{"type": "tool_result", "tool_use_id": "t1", "content": "data"}],
                ),
            ],
        )
        result = convert_to_messages(request)
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0]["type"] == "tool_result"


# ============================================================================
# Contract Tests
# ============================================================================


class TestContractTests:
    """Cross-service contract verification."""

    def test_process_response_contract_text(self):
        """Verify /v1/process text response is parseable by claude_proxy.py."""
        response = AIServiceResponse(
            content="Hello",
            model="claude-sonnet-4-5",
            provider="anthropic",
            metadata={"finish_reason": "stop", "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        )
        data = response.model_dump()
        assert isinstance(data["content"], str)
        assert data["content_blocks"] is None

    def test_process_response_contract_tool_use(self):
        """Verify /v1/process tool response carries content_blocks."""
        blocks = [
            {"type": "text", "text": "I'll search for that."},
            {"type": "tool_use", "id": "toolu_123", "name": "search", "input": {"q": "test"}},
        ]
        response = AIServiceResponse(
            content="I'll search for that.",
            content_blocks=blocks,
            model="claude-sonnet-4-5",
            provider="anthropic",
            metadata={"finish_reason": "tool_use", "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        )
        data = response.model_dump()
        assert isinstance(data["content"], str)  # Backward compat
        assert len(data["content_blocks"]) == 2
        assert data["content_blocks"][1]["type"] == "tool_use"
        assert data["metadata"]["finish_reason"] == "tool_use"
