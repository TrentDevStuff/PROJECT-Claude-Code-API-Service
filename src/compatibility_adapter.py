"""
Compatibility Adapter for AI Services API Format

Provides /v1/process endpoint that mirrors the production AI service API,
allowing prototypes to switch between services transparently.

Maps multi-provider requests to Claude Code models:
- provider="openai" + model="gpt-4" → sonnet
- provider="anthropic" + model="claude-3-opus" → opus
- provider="anthropic" + model="claude-3-sonnet" → sonnet
- provider="anthropic" + model="claude-3-haiku" → haiku
- All others → sonnet (default)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Message role types"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """Message format matching AI services"""

    id: str | None = None
    role: MessageRole
    content: str
    created_at: str | None = None
    metadata: dict[str, Any] | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


class ProcessRequest(BaseModel):
    """
    AI Services compatible request format.

    This mirrors the production ai-services API but only supports Claude Code.
    """

    # Required fields
    provider: str = Field(
        ..., description="AI provider (only 'anthropic' and 'claudecode' supported)"
    )
    model_name: str = Field(..., description="Model name (maps to haiku/sonnet/opus)")

    # Message options (use ONE of these approaches)
    messages: list[Message] | None = Field(None, description="Full conversation history")
    system_message: str | None = Field(None, description="System prompt")
    user_message: str | None = Field(None, description="User input")
    content: Any | None = Field(None, description="Multimodal content (text only for Claude Code)")

    # Generation parameters
    max_tokens: int | None = Field(1000, description="Maximum tokens to generate")
    temperature: float | None = Field(0.7, description="Sampling temperature")

    # Processing modes
    async_processing: bool = Field(False, description="Use async task queue")
    additional_params: dict[str, Any] | None = Field(
        None, description="Additional parameters (stream, etc.)"
    )

    # Features (unsupported - will be ignored with warning)
    tools: list[dict] | None = Field(None, description="Tool calling (not supported)")
    tool_choice: str | None = Field(None, description="Tool selection (not supported)")
    output_schema: dict | None = Field(None, description="Structured outputs (not supported)")
    media_content: list[dict] | None = Field(None, description="Multimodal content (not supported)")
    memory: dict | None = Field(None, description="Memory management (not supported)")

    # Execution path control (SDK is default for speed; CLI needed for tools/agents/MCP)
    use_cli: bool = Field(
        False,
        description="Use Claude CLI instead of SDK. Required for tools, agents, skills, MCP, working directory context.",
    )

    # Metadata
    project_id: str | None = Field("default", description="Project identifier for budget tracking")


class AIServiceResponse(BaseModel):
    """
    AI Services compatible response format.

    Mirrors production ai-services response structure.
    """

    content: str = Field(..., description="Response content")
    model: str = Field(..., description="Model used")
    provider: str = Field("claudecode", description="Provider name")
    metadata: dict[str, Any] = Field(..., description="Response metadata")


def map_model_to_claude(provider: str, model_name: str) -> str:
    """
    Map provider/model combinations to Claude Code models.

    Args:
        provider: Provider name (openai, anthropic, etc.)
        model_name: Model identifier

    Returns:
        Claude model: "haiku", "sonnet", or "opus"

    Mapping strategy:
    - Anthropic models → map directly
    - OpenAI mini/small models → haiku
    - OpenAI gpt-4, gemini-pro → sonnet
    - OpenAI gpt-4-turbo, o1, opus → opus
    - Default → sonnet
    """
    model_lower = model_name.lower()

    # Direct Anthropic mapping
    if "haiku" in model_lower:
        return "haiku"
    elif "opus" in model_lower:
        return "opus"
    elif "sonnet" in model_lower or "claude" in model_lower:
        return "sonnet"

    # OpenAI mapping (by capability)
    elif "gpt-3.5" in model_lower or "mini" in model_lower or "nano" in model_lower:
        return "haiku"  # Fast, cheap models
    elif "gpt-4-turbo" in model_lower or "gpt-4o" in model_lower or "o1" in model_lower:
        return "opus"  # Most capable
    elif "gpt-4" in model_lower or "gpt-5" in model_lower:
        return "sonnet"  # Balanced

    # Google mapping
    elif "gemini" in model_lower:
        if "flash" in model_lower:
            return "haiku"
        else:
            return "sonnet"

    # DeepSeek, LMStudio, others → default
    else:
        return "sonnet"


def convert_to_messages(request: ProcessRequest) -> list[dict[str, str]]:
    """
    Convert AI services request to OpenAI-style messages.

    Supports:
    - messages array (pass through)
    - system_message + user_message (convert)
    - content field (convert)
    """
    # If messages provided, use them
    if request.messages:
        return [{"role": msg.role.value, "content": msg.content} for msg in request.messages]

    # Build from legacy fields
    messages = []

    if request.system_message:
        messages.append({"role": "system", "content": request.system_message})

    if request.user_message:
        messages.append({"role": "user", "content": request.user_message})
    elif request.content:
        # If content is string, use it
        if isinstance(request.content, str):
            messages.append({"role": "user", "content": request.content})
        # If content is list (multimodal), extract text
        elif isinstance(request.content, list):
            text_parts = [
                part.get("text", part.get("content", ""))
                for part in request.content
                if part.get("type") == "text"
            ]
            messages.append({"role": "user", "content": " ".join(text_parts)})

    return messages


def convert_response(
    claude_response: dict[str, Any], original_provider: str, original_model: str, claude_model: str
) -> AIServiceResponse:
    """
    Convert Claude Code response to AI services format.

    Args:
        claude_response: Response from our worker pool
        original_provider: Provider from request
        original_model: Model name from request
        claude_model: Actual Claude model used

    Returns:
        AI services compatible response
    """
    return AIServiceResponse(
        content=claude_response.get("content", ""),
        model=original_model,  # Return what they requested
        provider=original_provider,
        metadata={
            "actual_model": claude_model,  # What we actually used
            "usage": claude_response.get("usage", {}),
            "cost_usd": claude_response.get("cost", 0),
            "processing_time": 0,  # TODO: Track this
            "finish_reason": "stop",
            "mapped_from": f"{original_provider}:{original_model} → claudecode:{claude_model}",
        },
    )
