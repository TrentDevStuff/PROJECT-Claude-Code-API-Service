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
import httpx

from src.settings import settings
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
        self.client = anthropic.Anthropic(
            max_retries=settings.sdk_max_retries,
            timeout=httpx.Timeout(settings.sdk_timeout_seconds, connect=10.0),
        )
        logger.info(
            "Direct completion client initialized (max_retries=%d, timeout=%.0fs)",
            settings.sdk_max_retries,
            settings.sdk_timeout_seconds,
        )

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

        except anthropic.RateLimitError as e:
            retry_after = None
            if hasattr(e, "response") and e.response is not None:
                ra_val = e.response.headers.get("retry-after")
                if ra_val:
                    try:
                        retry_after = float(ra_val)
                    except (ValueError, TypeError):
                        pass
            logger.warning(
                "Anthropic rate limit hit",
                extra={"error_category": "rate_limited", "upstream_status": 429, "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Rate limited by Anthropic API: {e}",
                error_category="rate_limited",
                upstream_status=429,
                retry_after=retry_after,
            )
        except anthropic.InternalServerError as e:
            status_code = getattr(e, "status_code", 500)
            category = "overloaded" if status_code == 529 else "upstream_error"
            logger.warning(
                "Anthropic server error (%d)",
                status_code,
                extra={"error_category": category, "upstream_status": status_code, "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic server error ({status_code}): {e}",
                error_category=category,
                upstream_status=status_code,
            )
        except anthropic.APITimeoutError as e:
            logger.warning(
                "Anthropic API timeout",
                extra={"error_category": "timeout", "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic API timeout: {e}",
                error_category="timeout",
            )
        except anthropic.APIConnectionError as e:
            logger.warning(
                "Anthropic API connection error",
                extra={"error_category": "connection_error", "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic API connection error: {e}",
                error_category="connection_error",
            )
        except anthropic.AuthenticationError as e:
            logger.error(
                "Anthropic auth error",
                extra={"error_category": "auth_error", "upstream_status": 401, "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic auth error: {e}",
                error_category="auth_error",
                upstream_status=401,
            )
        except anthropic.BadRequestError as e:
            logger.error(
                "Bad request to Anthropic API",
                extra={"error_category": "bad_request", "upstream_status": 400, "model": model_id},
            )
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Bad request to Anthropic API: {e}",
                error_category="bad_request",
                upstream_status=400,
            )
        except anthropic.APIError as e:
            logger.error("SDK API error: %s", e)
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Anthropic API error: {e}",
                error_category="upstream_error",
            )
        except Exception as e:
            logger.error("SDK completion error: %s", e)
            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.FAILED,
                error=f"Direct completion error: {e}",
                error_category="internal_error",
            )
