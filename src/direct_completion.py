"""
Direct Anthropic SDK completion path.

Bypasses the Claude CLI for simple completion requests, eliminating
3-8 seconds of CLI cold start overhead. Uses the Anthropic Messages API
directly via the Python SDK.

Supports tool calling when TOOL_PASSTHROUGH_ENABLED=true.
"""

from __future__ import annotations

import logging
import time

import anthropic
import httpx

from src.settings import settings
from src.worker_pool import TaskResult, TaskStatus

logger = logging.getLogger(__name__)

# Model short name → Anthropic API model ID.
# Use the bare aliases (no date suffix) — those are stable per Anthropic's
# model reference. A stale date suffix returns 404 not_found_error on the
# Messages API. Callers may also pass a full model ID (e.g.
# "claude-opus-4-7") directly; it's passed through unchanged.
MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
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

    def _validate_tools(self, tools: list[dict]) -> None:
        """Validate tool definitions at boundary. Log warnings, don't reject."""
        for i, tool in enumerate(tools):
            name = tool.get("name", f"tool_{i}")
            if not tool.get("name"):
                logger.warning("tool_validation_warning", extra={"tool_index": i, "issue": "missing_name"})
            if not tool.get("description"):
                logger.warning("tool_validation_warning", extra={"tool_name": name, "issue": "missing_description"})
            schema = tool.get("input_schema", {})
            if schema and schema.get("type") != "object":
                logger.warning("tool_validation_warning", extra={"tool_name": name, "issue": "input_schema_type_not_object"})

    @staticmethod
    def _apply_cache_markers(kwargs: dict) -> int:
        """Annotate the request with ``cache_control`` markers in-place.

        Render order is ``tools`` → ``system`` → ``messages``. Each marker
        caches the full prefix up to and including the marked block, so we
        place at most two breakpoints:

        1. On the last system text block (or, if no system, on the last tool)
           to cache the tools + system prefix. This prefix is usually stable
           across a session and shared across conversations that use the
           same tools.
        2. On the last user message's last content block to cache the full
           message history. Each follow-up turn then reads the prior history
           from cache instead of re-processing it.

        The Anthropic minimum-cacheable-prefix rule (4096 tokens on Opus 4.5+,
        2048 on Sonnet 4.6) means short prompts silently won't cache — no
        write cost is charged, so this is safe to enable unconditionally.

        Returns the number of cache_control breakpoints applied (for logging).
        """
        breakpoints = 0

        # --- Breakpoint 1: end of tools + system prefix -------------------
        system = kwargs.get("system")
        if isinstance(system, str) and system:
            # Upgrade to list-of-blocks form so we can attach cache_control.
            kwargs["system"] = [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]
            breakpoints += 1
        elif isinstance(system, list) and system:
            last = system[-1]
            if isinstance(last, dict):
                last["cache_control"] = {"type": "ephemeral"}
                breakpoints += 1
        else:
            # No system prompt — fall back to marking the last tool so the
            # tools prefix still gets cached on repeat requests.
            tools = kwargs.get("tools")
            if isinstance(tools, list) and tools and isinstance(tools[-1], dict):
                tools[-1]["cache_control"] = {"type": "ephemeral"}
                breakpoints += 1

        # --- Breakpoint 2: end of message history -------------------------
        # Place on the last user message's last content block so follow-up
        # turns can read the entire prior conversation from cache. The last
        # user message is the final user turn (before the assistant's next
        # response); placing the marker inside assistant or tool_result
        # content would work too but cluttering user content is simpler.
        messages = kwargs.get("messages") or []
        for msg in reversed(messages):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, str) and content:
                msg["content"] = [{
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }]
                breakpoints += 1
            elif isinstance(content, list) and content:
                last = content[-1]
                if isinstance(last, dict):
                    last["cache_control"] = {"type": "ephemeral"}
                    breakpoints += 1
            break

        return breakpoints

    def complete(
        self,
        messages: list[dict],
        model: str = "sonnet",
        max_tokens: int = 4096,
        system: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> TaskResult:
        """
        Send a completion request directly via the Anthropic Messages API.

        Args:
            messages: List of {"role": "...", "content": "..." or [content blocks]} dicts.
                      System messages are extracted and passed separately.
            model: Model short name (haiku/sonnet/opus) or full model ID.
            max_tokens: Maximum tokens to generate.
            system: Optional system prompt.
            tools: Optional tool definitions in Anthropic format.
            tool_choice: Optional tool selection preference.

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
                system_parts.append(content if isinstance(content, str) else str(content))
            else:
                # Preserve structured content (tool_result blocks, etc.)
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
            if tools:
                self._validate_tools(tools)
                kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

            # Apply prompt caching markers when enabled. Safe default — short
            # prefixes silently won't cache (no write cost); repeated prefixes
            # get ~90% input-cost reduction on cached tokens.
            cache_breakpoints = 0
            if settings.prompt_caching_enabled:
                cache_breakpoints = self._apply_cache_markers(kwargs)

            response = self.client.messages.create(**kwargs)

            # Extract content — preserve structure for tool calls
            content_blocks = []
            has_tool_use = False

            for block in response.content:
                if hasattr(block, "text"):
                    content_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    has_tool_use = True
                    content_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            # Audit log tool calls
            if has_tool_use:
                for block in content_blocks:
                    if block.get("type") == "tool_use":
                        logger.info(
                            "tool_call_passthrough",
                            extra={
                                "tool_name": block["name"],
                                "tool_id": block["id"],
                                "model": model_id,
                                "input_keys": list(block.get("input", {}).keys()),
                            },
                        )

            # Extract usage. Anthropic reports cache activity separately:
            #   input_tokens              — uncached portion (full rate)
            #   cache_creation_input_tokens — tokens written to cache this
            #                                request (1.25× for 5-min TTL)
            #   cache_read_input_tokens   — tokens served from cache this
            #                                request (~0.1× of input rate)
            # Fields are optional on older responses and may be None; coerce
            # to int so non-numeric defaults don't poison arithmetic below.
            def _safe_int(val) -> int:
                return val if isinstance(val, int) else 0

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cache_creation_tokens = _safe_int(
                getattr(response.usage, "cache_creation_input_tokens", 0)
            )
            cache_read_tokens = _safe_int(
                getattr(response.usage, "cache_read_input_tokens", 0)
            )

            # Calculate cost using Anthropic's multipliers.
            rates = COST_PER_MTK.get(model_short, COST_PER_MTK["sonnet"])
            input_rate = rates["input"] / 1_000_000
            output_rate = rates["output"] / 1_000_000
            cost = (
                input_tokens * input_rate
                + cache_creation_tokens * input_rate * 1.25
                + cache_read_tokens * input_rate * 0.1
                + output_tokens * output_rate
            )

            t_done = time.monotonic()
            # Cache hit ratio: reads / total prompt tokens. Useful for alerting
            # when a previously-cached prefix starts regressing to 0% hits
            # (the classic silent-invalidator failure mode).
            total_prompt_tokens = input_tokens + cache_creation_tokens + cache_read_tokens
            cache_hit_ratio = (
                round(cache_read_tokens / total_prompt_tokens, 3)
                if total_prompt_tokens > 0
                else 0.0
            )
            logger.info(
                "sdk_direct_completion",
                extra={
                    "model": model_id,
                    "latency_ms": round((t_done - t_start) * 1000, 1),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_tokens": cache_creation_tokens,
                    "cache_read_tokens": cache_read_tokens,
                    "cache_hit_ratio": cache_hit_ratio,
                    "cache_breakpoints": cache_breakpoints,
                    "has_tool_use": has_tool_use,
                },
            )

            # Build result — separate fields for text and structured content
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            completion_text = "".join(text_parts) if text_parts else None

            return TaskResult(
                task_id="sdk-direct",
                status=TaskStatus.COMPLETED,
                completion=completion_text,
                content_blocks=content_blocks if has_tool_use else None,
                stop_reason=response.stop_reason,
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
