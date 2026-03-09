"""Intelligent model selection based on task complexity, context size, and budget."""


def auto_select_model(prompt: str, context_size: int, budget_remaining: int) -> str:
    """
    Route to appropriate model based on prompt complexity, context size, and budget.

    Args:
        prompt: Task description/prompt text
        context_size: Estimated tokens needed (0 = simple, 10000+ = large)
        budget_remaining: Budget tokens left (0 = no budget)

    Returns:
        Model name: "haiku" | "sonnet" | "opus"
    """

    # Budget constraint: insufficient budget forces haiku
    if budget_remaining < 1000:
        return "haiku"

    # Context constraint: large context requires opus
    if context_size > 10000:
        return "opus"

    # Prompt length and complexity heuristics
    prompt_lower = prompt.lower()

    # Simple prompts (< 100 chars) with simple keywords → haiku
    if len(prompt) < 100:
        simple_keywords = ["list", "format", "count", "show", "get", "create", "add"]
        if any(kw in prompt_lower for kw in simple_keywords):
            return "haiku"

    # Complex reasoning keywords → sonnet (or opus if budget permits)
    complex_keywords = [
        "analyze",
        "architect",
        "debug",
        "design",
        "implement",
        "optimize",
        "refactor",
        "review",
        "test",
        "diagnose",
        "strategy",
    ]
    if any(kw in prompt_lower for kw in complex_keywords):
        if budget_remaining >= 5000:
            return "sonnet"
        else:
            return "haiku"

    # Default: sonnet for medium complexity
    return "sonnet"
