"""Token tracking and cost calculation for Claude API usage."""

import json
from decimal import Decimal
from typing import Any


class TokenTracker:
    """
    Tracks token usage and calculates costs for Claude API calls.

    Provides parsing of Claude CLI JSON output and cost calculation
    based on model pricing tiers.
    """

    # Model pricing per 1K tokens (USD)
    PRICING = {
        "haiku": {"input": Decimal("0.00025"), "output": Decimal("0.00125")},
        "sonnet": {"input": Decimal("0.003"), "output": Decimal("0.015")},
        "opus": {"input": Decimal("0.015"), "output": Decimal("0.075")},
    }

    @classmethod
    def parse_claude_output(cls, json_str: str) -> dict[str, Any]:
        """
        Parse Claude CLI JSON output to extract token usage and cost.

        Expected JSON format:
        {
            "usage": {
                "input_tokens": int,
                "output_tokens": int
            },
            "model": str  # e.g., "claude-3-haiku-20240307"
        }

        Args:
            json_str: JSON string from Claude CLI output

        Returns:
            Dictionary containing:
            {
                "input_tokens": int,
                "output_tokens": int,
                "total_tokens": int,
                "model": str,
                "model_tier": str,  # "haiku", "sonnet", or "opus"
                "cost_usd": float
            }

        Raises:
            ValueError: If JSON is invalid or missing required fields
            KeyError: If required fields are not present in JSON
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        # Extract usage data
        if "usage" not in data:
            raise KeyError("Missing 'usage' field in JSON")

        usage = data["usage"]

        if "input_tokens" not in usage:
            raise KeyError("Missing 'input_tokens' in usage")
        if "output_tokens" not in usage:
            raise KeyError("Missing 'output_tokens' in usage")

        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        total_tokens = input_tokens + output_tokens

        # Extract model information
        if "model" not in data:
            raise KeyError("Missing 'model' field in JSON")

        model_full_name = data["model"]

        # Determine model tier from full model name
        model_tier = cls._extract_model_tier(model_full_name)

        # Calculate cost
        cost_usd = cls.calculate_cost(input_tokens, output_tokens, model_tier)

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "model": model_full_name,
            "model_tier": model_tier,
            "cost_usd": float(cost_usd),
        }

    @classmethod
    def _extract_model_tier(cls, model_name: str) -> str:
        """
        Extract model tier from full model name.

        Args:
            model_name: Full model name (e.g., "claude-3-haiku-20240307")

        Returns:
            Model tier: "haiku", "sonnet", or "opus"

        Raises:
            ValueError: If model tier cannot be determined
        """
        model_lower = model_name.lower()

        if "haiku" in model_lower:
            return "haiku"
        elif "sonnet" in model_lower:
            return "sonnet"
        elif "opus" in model_lower:
            return "opus"
        else:
            raise ValueError(f"Unknown model tier in model name: {model_name}")

    @classmethod
    def calculate_cost(cls, input_tokens: int, output_tokens: int, model: str) -> Decimal:
        """
        Calculate cost in USD for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model tier ("haiku", "sonnet", or "opus")

        Returns:
            Cost in USD as Decimal for precision

        Raises:
            ValueError: If model is not recognized
        """
        model_lower = model.lower()

        if model_lower not in cls.PRICING:
            raise ValueError(
                f"Unknown model: {model}. " f"Valid models: {', '.join(cls.PRICING.keys())}"
            )

        pricing = cls.PRICING[model_lower]

        # Calculate cost: (tokens / 1000) * price_per_1k
        input_cost = (Decimal(input_tokens) / 1000) * pricing["input"]
        output_cost = (Decimal(output_tokens) / 1000) * pricing["output"]

        total_cost = input_cost + output_cost

        # Round to 6 decimal places for USD cents precision
        return total_cost.quantize(Decimal("0.000001"))
