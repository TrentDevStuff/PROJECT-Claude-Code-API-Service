"""Model routing commands"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from ..api_client import APIClient, APIError
from ..utils import format_cost, print_error, print_section, print_success

app = typer.Typer(help="Model routing recommendations")
console = Console()


@app.command()
def recommend(
    prompt: str = typer.Argument(..., help="Task description or prompt"),
    context_size: int = typer.Option(0, help="Estimated context size in tokens"),
    key: str = typer.Option(None, help="API key"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get model recommendation for a prompt"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        response = client.route_recommend(prompt=prompt, context_size=context_size)

        if json_output:
            print(json.dumps(response, indent=2, default=str))
            return

        print_section("Model Routing Recommendation")
        print()

        model = response.get("recommended_model", "N/A")
        reasoning = response.get("reasoning", "N/A")

        print_success(f"Recommended model: {model}")
        console.print(f"  Reasoning: {reasoning}")
        print()

        budget = response.get("budget_status", {})
        if budget:
            table = Table(title="Budget Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white", justify="right")

            table.add_row("Total tokens used", str(budget.get("total_tokens", 0)))
            table.add_row("Total cost", format_cost(budget.get("total_cost", 0)))

            limit = budget.get("limit")
            table.add_row("Limit", str(limit) if limit is not None else "Unlimited")

            remaining = budget.get("remaining")
            table.add_row("Remaining", str(remaining) if remaining is not None else "Unlimited")

            console.print(table)

    except APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
