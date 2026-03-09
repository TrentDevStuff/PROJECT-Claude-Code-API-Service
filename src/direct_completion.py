"""
Direct Anthropic SDK completion path.

Bypasses the Claude CLI for simple completion requests, eliminating
3-8 seconds of CLI cold start overhead. Uses the Anthropic Messages API
directly via the Python SDK.

Only suitable for simple completions without tools/agents/skills.
"""

from __future__ import annotations

import logging
import time

import anthropic

from src.worker_pool import TaskResult, TaskStatus

logger = logging.getLogger(__name__)

# Model name → Anthropic API model ID
MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6-20250514",
    "opus": "claude-opus-4-6-20250514",
    # Allow full model IDs to pass through
}

# Cost per million tokens (matches WorkerPool.COST_PER_MTK)
COST_PER_MTK = {
    "haiku": {"input": 0.25, "output": 1.25},
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 15.00, "output": 75.00},
}


class DirectCompletionClient:
    """
    Thin wrapper around the Anthropic Messages API.

    Maintains a persistent client instance (initialized once at startup)
    to avoid per-request connection overhead.
    """

    def __init__(self):
        """Initialize with Anthropic SDK client. Reads ANTHROPIC_API_KEY from env."""
        self.client = anthropic.Anthropic()
        logger.info("Direct completion client initialized")

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "sonnet",
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> TaskResult:
        """
        Send a completion request directly via the Anthropic Messages API.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."} dicts.
                      System messages are extracted and passed separately.
            model: Model short name (haiku/sonnet/opus) or full model ID.
            max_tokens: Maximum tokens to generate.
            system: Optional system prompt.

        Returns:
            TaskResult compatible with the worker pool interface.
        """
        t_start = time.monotonic()

        # Resolve model ID
        model_id = MODEL_MAP.get(model, model)
        model_short = model if model in MODEL_MAP else "sonnet"

        # Separate system messages from conversation messages
        api_messages = []
        system_parts = []
        if system:
            system_parts.append(system)

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                api_messages.append({"role": role, "content": content})

        # Ensure at least one user message
        if not api_messages:
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error="No user or assistant messages provided",
            )

        try:
            kwargs = {
                "model": model_id,
                "max_tokens": max_tokens,
                "messages": api_messages,
            }
            if system_parts:
                kwargs["system"] = "\n\n".join(system_parts)

            response = self.client.messages.create(**kwargs)

            # Extract content
            completion_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    completion_text += block.text

            # Extract usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Calculate cost
            rates = COST_PER_MTK.get(model_short, COST_PER_MTK["sonnet"])
            cost = (input_tokens / 1_000_000) * rates["input"] + (
                output_tokens / 1_000_000
            ) * rates["output"]

            t_done = time.monotonic()
            logger.info(
                "sdk_direct_completion",
                extra={
                    "model": model_id,
                    "latency_ms": round((t_done - t_start) * 1000, 1),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.COMPLETED,
                completion=completion_text,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                cost=cost,
            )

        except anthropic.APIError as e:
            logger.error("SDK API error: %s", e)
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic API error: {e}",
            )
        except Exception as e:
            logger.error("SDK completion error: %s", e)
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Direct completion error: {e}",
            )
