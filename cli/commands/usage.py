"""Usage analytics commands"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..api_client import APIClient
from ..utils import (
    format_cost,
    format_tokens,
    print_error,
    print_info,
    print_section,
    print_warning,
)

app = typer.Typer(help="Usage analytics")
console = Console()


@app.command()
def summary(
    period: str = typer.Option("month", help="Time period (day, week, month)"),
    key: str = typer.Option(None, help="API key"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Overall usage summary with per-model breakdown"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        usage = client.get_usage(period=period)

        if json_output:
            import json

            print(json.dumps(usage, indent=2, default=str))
            return

        print_section(f"Usage Summary (Period: {period})")
        print()

        # Summary table
        total_tokens = usage.get("total_tokens", 0)
        total_cost = usage.get("total_cost", 0)
        limit = usage.get("limit")
        remaining = usage.get("remaining")

        summary_table = Table(title="Overview")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="white", justify="right")

        summary_table.add_row("Total tokens", format_tokens(total_tokens))
        summary_table.add_row("Total cost", format_cost(total_cost))
        summary_table.add_row("Limit", format_tokens(limit) if limit is not None else "Unlimited")
        summary_table.add_row(
            "Remaining", format_tokens(remaining) if remaining is not None else "Unlimited"
        )

        console.print(summary_table)
        print()

        # Per-model breakdown
        by_model = usage.get("by_model", {})
        if by_model:
            model_table = Table(title="By Model")
            model_table.add_column("Model", style="cyan")
            model_table.add_column("Tokens", style="white", justify="right")
            model_table.add_column("Cost", style="white", justify="right")
            model_table.add_column("% of Total", style="white", justify="right")

            for model_name, stats in by_model.items():
                tokens = stats.get("tokens", 0)
                cost = stats.get("cost", 0)
                pct = (tokens / total_tokens * 100) if total_tokens > 0 else 0
                model_table.add_row(
                    model_name,
                    format_tokens(tokens),
                    format_cost(cost),
                    f"{pct:.1f}%",
                )

            console.print(model_table)

    except Exception as e:
        print_error(f"Failed to get usage summary: {str(e)}")
        raise typer.Exit(1)


@app.command()
def by_project(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Usage breakdown by project"""

    try:
        APIClient()  # validate service is reachable

        # Get all keys and their projects
        print_info("Aggregating usage by project...")

        # Placeholder - would need API endpoint for this
        print_warning("Project-level analytics endpoint not yet implemented in API")
        print_info("Run 'claude-api keys list' to see projects")

    except Exception as e:
        print_error(f"Failed to get project usage: {str(e)}")
        raise typer.Exit(1)


@app.command()
def by_model(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Usage breakdown by model"""

    try:
        print_warning("Model-level analytics endpoint not yet implemented in API")
        print_info("This feature requires API enhancement")

    except Exception as e:
        print_error(f"Failed to get model usage: {str(e)}")
        raise typer.Exit(1)


@app.command()
def costs(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Cost breakdown"""

    try:
        print_warning("Cost analytics endpoint not yet implemented in API")
        print_info("This feature requires API enhancement")

    except Exception as e:
        print_error(f"Failed to get costs: {str(e)}")
        raise typer.Exit(1)


@app.command()
def export(
    format: str = typer.Option("csv", help="Export format (csv, json)"),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export usage data"""

    try:
        print_warning("Usage export endpoint not yet implemented in API")
        print_info("This feature requires API enhancement")

    except Exception as e:
        print_error(f"Failed to export usage: {str(e)}")
        raise typer.Exit(1)
