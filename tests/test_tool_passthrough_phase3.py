"""
Phase 3 tests: Tool Calling Passthrough — IL CLI Path (/v1/chat/completions).

Tests cover:
- OpenAI → Anthropic tool translation
- Anthropic → OpenAI response translation
- Tool choice translation
- System message extraction
- Message format conversion (tool, assistant with tool_calls)
- Contract tests matching executor.py expectations
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from src.tool_translation import (
    anthropic_result_to_openai_response,
    openai_messages_to_anthropic,
    openai_tool_choice_to_anthropic,
    openai_tools_to_anthropic,
)
from src.worker_pool import TaskResult, TaskStatus


# ============================================================================
# OpenAI → Anthropic Tool Definition Translation
# ============================================================================


class TestOpenAIToAnthropicTools:
    """Test openai_tools_to_anthropic."""

    def test_wrapped_function_format(self):
        """OpenAI {type: "function", function: {parameters}} → {input_schema}."""
        tools = [{
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the database",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        }]
        result = openai_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "Search the database"
        assert result[0]["input_schema"]["type"] == "object"

    def test_unwrapped_format(self):
        """Direct {name, description, parameters} (no wrapper) also works."""
        tools = [{
            "name": "calc",
            "description": "Calculate",
            "parameters": {"type": "object", "properties": {"expr": {"type": "string"}}},
        }]
        result = openai_tools_to_anthropic(tools)
        assert result[0]["name"] == "calc"
        assert result[0]["input_schema"]["properties"]["expr"]["type"] == "string"

    def test_missing_parameters_defaults(self):
        """Missing parameters gets default empty object schema."""
        tools = [{"type": "function", "function": {"name": "noop", "description": "No-op"}}]
        result = openai_tools_to_anthropic(tools)
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}


# ============================================================================
# OpenAI → Anthropic Message Translation
# ============================================================================


class TestOpenAIToAnthropicMessages:
    """Test openai_messages_to_anthropic."""

    def test_system_message_extraction(self):
        """System messages extracted and returned separately."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result, system = openai_messages_to_anthropic(messages)
        assert system == "You are helpful."
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_tool_result_to_anthropic(self):
        """role: 'tool' message → user message with tool_result block."""
        messages = [
            {"role": "tool", "content": "Found 3 results", "tool_call_id": "call_abc"},
        ]
        result, _ = openai_messages_to_anthropic(messages)
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["type"] == "tool_result"
        assert result[0]["content"][0]["tool_use_id"] == "call_abc"
        assert result[0]["content"][0]["content"] == "Found 3 results"

    def test_assistant_tool_calls_to_anthropic(self):
        """Assistant message with tool_calls → tool_use content blocks."""
        messages = [{
            "role": "assistant",
            "content": "Searching...",
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }],
        }]
        result, _ = openai_messages_to_anthropic(messages)
        assert result[0]["role"] == "assistant"
        blocks = result[0]["content"]
        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == "Searching..."
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["name"] == "search"
        assert blocks[1]["input"] == {"q": "test"}

    def test_arguments_json_string_parsed(self):
        """function.arguments (JSON string) → input (object)."""
        messages = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "x", "arguments": '{"a": 1, "b": "hello"}'},
            }],
        }]
        result, _ = openai_messages_to_anthropic(messages)
        tool_block = result[0]["content"][0]  # No text block since content=""
        assert tool_block["input"] == {"a": 1, "b": "hello"}

    def test_malformed_arguments_fallback(self):
        """Invalid JSON arguments fall back to empty dict."""
        messages = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "x", "arguments": "not valid json"},
            }],
        }]
        result, _ = openai_messages_to_anthropic(messages)
        tool_block = result[0]["content"][0]
        assert tool_block["input"] == {}


# ============================================================================
# OpenAI → Anthropic Tool Choice Translation
# ============================================================================


class TestToolChoiceTranslation:
    """Test openai_tool_choice_to_anthropic."""

    def test_auto(self):
        assert openai_tool_choice_to_anthropic("auto") == {"type": "auto"}

    def test_required(self):
        assert openai_tool_choice_to_anthropic("required") == {"type": "any"}

    def test_none_string(self):
        assert openai_tool_choice_to_anthropic("none") is None

    def test_none_value(self):
        assert openai_tool_choice_to_anthropic(None) is None

    def test_specific_function(self):
        choice = {"type": "function", "function": {"name": "search"}}
        result = openai_tool_choice_to_anthropic(choice)
        assert result == {"type": "tool", "name": "search"}


# ============================================================================
# Anthropic → OpenAI Response Translation
# ============================================================================


class TestAnthropicResultToOpenAI:
    """Test anthropic_result_to_openai_response."""

    def test_text_only_response(self):
        """Text-only TaskResult → OpenAI response with content string."""
        result = TaskResult(
            task_id="sdk-direct",
            status=TaskStatus.COMPLETED,
            completion="Hello world",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            cost=0.001,
        )
        response = anthropic_result_to_openai_response(result, "sonnet", "proj-1")
        assert response["choices"][0]["message"]["content"] == "Hello world"
        assert response["choices"][0]["finish_reason"] == "stop"
        assert not response["choices"][0]["message"].get("tool_calls")

    def test_tool_use_response(self):
        """TaskResult with content_blocks → OpenAI tool_calls array."""
        result = TaskResult(
            task_id="sdk-direct",
            status=TaskStatus.COMPLETED,
            completion="Searching...",
            content_blocks=[
                {"type": "text", "text": "Searching..."},
                {"type": "tool_use", "id": "toolu_123", "name": "search", "input": {"q": "test"}},
            ],
            stop_reason="tool_use",
            usage={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            cost=0.002,
        )
        response = anthropic_result_to_openai_response(result, "sonnet", "proj-1")
        msg = response["choices"][0]["message"]
        assert msg["tool_calls"] is not None
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["function"]["name"] == "search"
        assert json.loads(tc["function"]["arguments"]) == {"q": "test"}
        assert response["choices"][0]["finish_reason"] == "tool_calls"

    def test_tool_use_arguments_are_json_string(self):
        """tool_use.input (object) → function.arguments (JSON string)."""
        result = TaskResult(
            task_id="t1",
            status=TaskStatus.COMPLETED,
            content_blocks=[
                {"type": "tool_use", "id": "t1", "name": "x", "input": {"a": 1}},
            ],
            stop_reason="tool_use",
            usage={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        )
        response = anthropic_result_to_openai_response(result, "sonnet", "p1")
        args = response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args, str)
        assert json.loads(args) == {"a": 1}


# ============================================================================
# Contract Tests — Match executor.py Expectations
# ============================================================================


class TestContractTests:
    """Verify response format matches what executor.py parses."""

    def test_tool_response_matches_executor(self):
        """Verify tool_calls response format matches executor parsing."""
        result = TaskResult(
            task_id="sdk-direct",
            status=TaskStatus.COMPLETED,
            content_blocks=[
                {"type": "tool_use", "id": "call_123", "name": "query_entities", "input": {"label": "Task"}},
            ],
            stop_reason="tool_use",
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            cost=0.01,
        )
        response = anthropic_result_to_openai_response(result, "sonnet", "proj-1")

        # Simulate executor.py parsing
        choices = response.get("choices", [])
        assert choices
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        assert len(tool_calls) == 1
        func = tool_calls[0].get("function", {})
        assert func["name"] == "query_entities"
        args = json.loads(func["arguments"])
        assert args == {"label": "Task"}

    def test_text_response_matches_executor(self):
        """Verify text-only response matches executor expectations."""
        result = TaskResult(
            task_id="sdk-direct",
            status=TaskStatus.COMPLETED,
            completion="Here are the results...",
            usage={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
            cost=0.005,
        )
        response = anthropic_result_to_openai_response(result, "sonnet", "proj-1")

        choices = response.get("choices", [])
        message = choices[0].get("message", {})
        assert message.get("content") == "Here are the results..."
        assert not message.get("tool_calls")
