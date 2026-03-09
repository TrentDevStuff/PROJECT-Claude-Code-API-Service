"""Tests for TokenTracker class."""

import json
from decimal import Decimal

import pytest

from src.token_tracker import TokenTracker


class TestParseClaudeOutput:
    """Tests for parse_claude_output method."""

    def test_parse_valid_haiku_output(self):
        """Test parsing valid Haiku model output."""
        json_output = json.dumps(
            {
                "usage": {"input_tokens": 1000, "output_tokens": 500},
                "model": "claude-3-haiku-20240307",
            }
        )

        result = TokenTracker.parse_claude_output(json_output)

        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["total_tokens"] == 1500
        assert result["model"] == "claude-3-haiku-20240307"
        assert result["model_tier"] == "haiku"
        assert isinstance(result["cost_usd"], float)
        assert result["cost_usd"] > 0

    def test_parse_valid_sonnet_output(self):
        """Test parsing valid Sonnet model output."""
        json_output = json.dumps(
            {
                "usage": {"input_tokens": 2000, "output_tokens": 1000},
                "model": "claude-3-sonnet-20240229",
            }
        )

        result = TokenTracker.parse_claude_output(json_output)

        assert result["input_tokens"] == 2000
        assert result["output_tokens"] == 1000
        assert result["total_tokens"] == 3000
        assert result["model"] == "claude-3-sonnet-20240229"
        assert result["model_tier"] == "sonnet"
        assert isinstance(result["cost_usd"], float)

    def test_parse_valid_opus_output(self):
        """Test parsing valid Opus model output."""
        json_output = json.dumps(
            {
                "usage": {"input_tokens": 500, "output_tokens": 250},
                "model": "claude-3-opus-20240229",
            }
        )

        result = TokenTracker.parse_claude_output(json_output)

        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 250
        assert result["total_tokens"] == 750
        assert result["model"] == "claude-3-opus-20240229"
        assert result["model_tier"] == "opus"
        assert isinstance(result["cost_usd"], float)

    def test_parse_zero_tokens(self):
        """Test parsing output with zero tokens."""
        json_output = json.dumps(
            {"usage": {"input_tokens": 0, "output_tokens": 0}, "model": "claude-3-haiku-20240307"}
        )

        result = TokenTracker.parse_claude_output(json_output)

        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["total_tokens"] == 0
        assert result["cost_usd"] == 0.0

    def test_parse_large_token_counts(self):
        """Test parsing with large token counts."""
        json_output = json.dumps(
            {
                "usage": {"input_tokens": 100000, "output_tokens": 50000},
                "model": "claude-3-sonnet-20240229",
            }
        )

        result = TokenTracker.parse_claude_output(json_output)

        assert result["input_tokens"] == 100000
        assert result["output_tokens"] == 50000
        assert result["total_tokens"] == 150000
        # Should calculate correctly for large numbers
        expected_cost = (100000 / 1000) * 0.003 + (50000 / 1000) * 0.015
        assert abs(result["cost_usd"] - expected_cost) < 0.000001


class TestInvalidJsonHandling:
    """Tests for invalid JSON handling."""

    def test_invalid_json_syntax(self):
        """Test handling of malformed JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            TokenTracker.parse_claude_output("{invalid json}")

    def test_missing_usage_field(self):
        """Test handling of missing usage field."""
        json_output = json.dumps({"model": "claude-3-haiku-20240307"})

        with pytest.raises(KeyError, match="Missing 'usage' field"):
            TokenTracker.parse_claude_output(json_output)

    def test_missing_input_tokens(self):
        """Test handling of missing input_tokens."""
        json_output = json.dumps(
            {"usage": {"output_tokens": 500}, "model": "claude-3-haiku-20240307"}
        )

        with pytest.raises(KeyError, match="Missing 'input_tokens'"):
            TokenTracker.parse_claude_output(json_output)

    def test_missing_output_tokens(self):
        """Test handling of missing output_tokens."""
        json_output = json.dumps(
            {"usage": {"input_tokens": 1000}, "model": "claude-3-haiku-20240307"}
        )

        with pytest.raises(KeyError, match="Missing 'output_tokens'"):
            TokenTracker.parse_claude_output(json_output)

    def test_missing_model_field(self):
        """Test handling of missing model field."""
        json_output = json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 500}})

        with pytest.raises(KeyError, match="Missing 'model' field"):
            TokenTracker.parse_claude_output(json_output)

    def test_unknown_model_tier(self):
        """Test handling of unknown model tier."""
        json_output = json.dumps(
            {"usage": {"input_tokens": 1000, "output_tokens": 500}, "model": "claude-unknown-model"}
        )

        with pytest.raises(ValueError, match="Unknown model tier"):
            TokenTracker.parse_claude_output(json_output)

    def test_empty_string(self):
        """Test handling of empty string."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            TokenTracker.parse_claude_output("")

    def test_non_json_string(self):
        """Test handling of non-JSON string."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            TokenTracker.parse_claude_output("not json at all")


class TestCalculateCost:
    """Tests for calculate_cost method."""

    def test_haiku_cost_calculation(self):
        """Test cost calculation for Haiku model."""
        cost = TokenTracker.calculate_cost(1000, 500, "haiku")

        # 1000 input tokens: (1000/1000) * 0.00025 = 0.00025
        # 500 output tokens: (500/1000) * 0.00125 = 0.000625
        # Total: 0.000875
        expected = Decimal("0.000875")
        assert cost == expected

    def test_sonnet_cost_calculation(self):
        """Test cost calculation for Sonnet model."""
        cost = TokenTracker.calculate_cost(2000, 1000, "sonnet")

        # 2000 input tokens: (2000/1000) * 0.003 = 0.006
        # 1000 output tokens: (1000/1000) * 0.015 = 0.015
        # Total: 0.021
        expected = Decimal("0.021")
        assert cost == expected

    def test_opus_cost_calculation(self):
        """Test cost calculation for Opus model."""
        cost = TokenTracker.calculate_cost(500, 250, "opus")

        # 500 input tokens: (500/1000) * 0.015 = 0.0075
        # 250 output tokens: (250/1000) * 0.075 = 0.01875
        # Total: 0.02625
        expected = Decimal("0.02625")
        assert cost == expected

    def test_zero_tokens_cost(self):
        """Test cost calculation with zero tokens."""
        cost = TokenTracker.calculate_cost(0, 0, "haiku")
        assert cost == Decimal("0.0")

    def test_only_input_tokens(self):
        """Test cost calculation with only input tokens."""
        cost = TokenTracker.calculate_cost(1000, 0, "haiku")

        expected = Decimal("0.00025")
        assert cost == expected

    def test_only_output_tokens(self):
        """Test cost calculation with only output tokens."""
        cost = TokenTracker.calculate_cost(0, 1000, "haiku")

        expected = Decimal("0.00125")
        assert cost == expected

    def test_large_token_counts(self):
        """Test cost calculation with large token counts."""
        cost = TokenTracker.calculate_cost(1000000, 500000, "sonnet")

        # 1M input: (1000000/1000) * 0.003 = 3.0
        # 500K output: (500000/1000) * 0.015 = 7.5
        # Total: 10.5
        expected = Decimal("10.5")
        assert cost == expected

    def test_fractional_token_precision(self):
        """Test precision with fractional calculations."""
        cost = TokenTracker.calculate_cost(123, 456, "haiku")

        # Should maintain precision to 6 decimal places
        assert isinstance(cost, Decimal)
        # Verify it's rounded to 6 decimal places
        assert len(str(cost).split(".")[-1]) <= 6

    def test_case_insensitive_model_name(self):
        """Test that model names are case-insensitive."""
        cost_lower = TokenTracker.calculate_cost(1000, 500, "haiku")
        cost_upper = TokenTracker.calculate_cost(1000, 500, "HAIKU")
        cost_mixed = TokenTracker.calculate_cost(1000, 500, "Haiku")

        assert cost_lower == cost_upper == cost_mixed

    def test_invalid_model_name(self):
        """Test handling of invalid model name."""
        with pytest.raises(ValueError, match="Unknown model"):
            TokenTracker.calculate_cost(1000, 500, "invalid-model")

    def test_cost_return_type(self):
        """Test that cost is returned as Decimal."""
        cost = TokenTracker.calculate_cost(1000, 500, "haiku")
        assert isinstance(cost, Decimal)


class TestIntegrationWithBudgetManager:
    """Integration tests with BudgetManager."""

    def test_parsed_output_compatible_with_budget_manager(self):
        """Test that parsed output format is compatible with BudgetManager.track_usage."""
        json_output = json.dumps(
            {
                "usage": {"input_tokens": 1000, "output_tokens": 500},
                "model": "claude-3-haiku-20240307",
            }
        )

        result = TokenTracker.parse_claude_output(json_output)

        # Verify all required fields for BudgetManager.track_usage are present
        assert "model_tier" in result or "model" in result
        assert "total_tokens" in result
        assert "cost_usd" in result

        # Verify types are correct
        assert isinstance(result["total_tokens"], int)
        assert isinstance(result["cost_usd"], float)

    def test_cost_calculation_matches_pricing_spec(self):
        """Verify cost calculations match the pricing specification."""
        # Test all three models with known values
        test_cases = [
            {
                "model": "haiku",
                "input": 1000,
                "output": 1000,
                "expected": 0.00025 + 0.00125,  # 0.0015
            },
            {"model": "sonnet", "input": 1000, "output": 1000, "expected": 0.003 + 0.015},  # 0.018
            {"model": "opus", "input": 1000, "output": 1000, "expected": 0.015 + 0.075},  # 0.090
        ]

        for case in test_cases:
            cost = TokenTracker.calculate_cost(case["input"], case["output"], case["model"])
            assert abs(float(cost) - case["expected"]) < 0.000001
