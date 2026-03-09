"""Tests for model auto-routing logic."""

from src.model_router import auto_select_model


def test_simple_routes_to_haiku():
    """Simple prompts with simple keywords should route to haiku."""
    result = auto_select_model(prompt="list all files", context_size=100, budget_remaining=5000)
    assert result == "haiku"

    result = auto_select_model(prompt="format json", context_size=500, budget_remaining=3000)
    assert result == "haiku"


def test_complex_routes_to_sonnet():
    """Complex prompts with complex keywords should route to sonnet."""
    result = auto_select_model(
        prompt="analyze the codebase structure and provide recommendations",
        context_size=500,
        budget_remaining=5000,
    )
    assert result == "sonnet"

    result = auto_select_model(
        prompt="debug this authentication bug in the API layer",
        context_size=2000,
        budget_remaining=8000,
    )
    assert result == "sonnet"


def test_large_context_routes_to_opus():
    """Large context (>10k tokens) should route to opus."""
    result = auto_select_model(
        prompt="analyze this large dataset", context_size=15000, budget_remaining=10000
    )
    assert result == "opus"

    result = auto_select_model(
        prompt="implement this feature", context_size=50000, budget_remaining=20000
    )
    assert result == "opus"


def test_low_budget_forces_haiku():
    """Budget < 1000 tokens should force haiku."""
    result = auto_select_model(
        prompt="analyze complex architecture", context_size=100, budget_remaining=500
    )
    assert result == "haiku"

    result = auto_select_model(prompt="debug the system", context_size=5000, budget_remaining=999)
    assert result == "haiku"


def test_default_routing():
    """Prompts without special keywords should default to sonnet."""
    result = auto_select_model(
        prompt="help me with this task", context_size=2000, budget_remaining=5000
    )
    assert result == "sonnet"

    result = auto_select_model(
        prompt="what do you think about this", context_size=1000, budget_remaining=4000
    )
    assert result == "sonnet"


def test_constraints_override_defaults():
    """Constraints should override keyword-based routing."""
    # Large context overrides keyword routing
    result = auto_select_model(prompt="list all items", context_size=20000, budget_remaining=10000)
    assert result == "opus"

    # Low budget overrides complex keywords
    result = auto_select_model(
        prompt="optimize and refactor the entire system", context_size=100, budget_remaining=500
    )
    assert result == "haiku"
