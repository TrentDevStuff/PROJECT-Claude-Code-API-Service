"""
Bidirectional OpenAI ↔ Anthropic tool format translation.

Used by /v1/chat/completions to translate IL CLI requests (OpenAI format)
to Anthropic format for DirectCompletionClient, and translate responses back.

Structured identically to the translation functions in claude_proxy.py
(port 8005) for future extraction to a shared package.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# OpenAI → Anthropic (request direction)
# ============================================================================


def openai_tools_to_anthropic(openai_tools: list[dict]) -> list[dict]:
    """
    Translate OpenAI tool definitions to Anthropic format.

    OpenAI: {type: "function", function: {name, description, parameters}}
    Anthropic: {name, description, input_schema}
    """
    anthropic_tools = []
    for tool in openai_tools:
        if not isinstance(tool, dict):
            continue
        func = tool.get("function", tool)  # Handle both wrapped and unwrapped
        anthropic_tools.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


def openai_messages_to_anthropic(
    messages: list[dict],
) -> tuple[list[dict], str | None]:
    """
    Translate OpenAI message format to Anthropic format.

    Handles:
    - role: "system" → extracted to separate system string
    - role: "tool" → user message with tool_result content block
    - role: "assistant" with tool_calls → assistant with tool_use content blocks
    - role: "user"/"assistant" → pass through

    Returns: (anthropic_messages, system_string_or_none)
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            system_parts.append(content if isinstance(content, str) else str(content))

        elif role == "tool":
            # OpenAI tool result → Anthropic tool_result content block
            tool_call_id = msg.get("tool_call_id", "")
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content if isinstance(content, str) else str(content),
                }],
            })

        elif role == "assistant" and msg.get("tool_calls"):
            # OpenAI assistant with tool_calls → Anthropic assistant with tool_use blocks
            blocks: list[dict] = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                args = func.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                    "name": func.get("name", ""),
                    "input": args,
                })
            anthropic_messages.append({"role": "assistant", "content": blocks})

        else:
            # Regular user/assistant message
            anthropic_messages.append({"role": role, "content": content})

    system = "\n\n".join(system_parts) if system_parts else None
    return anthropic_messages, system


def openai_tool_choice_to_anthropic(choice: str | dict | None) -> dict | None:
    """
    Translate OpenAI tool_choice to Anthropic format.

    "auto" → {"type": "auto"}
    "required" → {"type": "any"}
    "none" → None (Anthropic doesn't have a direct equivalent)
    {"type": "function", "function": {"name": "X"}} → {"type": "tool", "name": "X"}
    """
    if choice is None:
        return None
    if isinstance(choice, str):
        mapping = {"auto": {"type": "auto"}, "required": {"type": "any"}, "none": None}
        return mapping.get(choice)
    if isinstance(choice, dict) and choice.get("type") == "function":
        name = choice.get("function", {}).get("name", "")
        return {"type": "tool", "name": name}
    return None


# ============================================================================
# Anthropic → OpenAI (response direction)
# ============================================================================


def anthropic_result_to_openai_response(
    result: Any,
    model: str,
    project_id: str,
) -> dict:
    """
    Convert DirectCompletionClient TaskResult to OpenAI-compatible response.

    Handles both text-only and tool_use responses.
    """
    msg: dict[str, Any] = {"role": "assistant", "content": None}
    finish_reason = "stop"

    if result.content_blocks:
        tool_calls = []
        text_parts = []

        for block in result.content_blocks:
            if block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        if tool_calls:
            msg["tool_calls"] = tool_calls
            msg["content"] = "".join(text_parts) if text_parts else None
            finish_reason = "tool_calls"
        else:
            msg["content"] = "".join(text_parts)
            finish_reason = "stop"

    elif result.completion:
        msg["content"] = result.completion
        finish_reason = "stop"
    else:
        msg["content"] = ""
        finish_reason = "stop"

    return {
        "id": result.task_id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": model or "unknown",
        "choices": [{"index": 0, "message": msg, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": (result.usage or {}).get("input_tokens", 0),
            "completion_tokens": (result.usage or {}).get("output_tokens", 0),
            "total_tokens": (result.usage or {}).get("total_tokens", 0),
        },
        "cost": result.cost,
        "project_id": project_id,
    }
