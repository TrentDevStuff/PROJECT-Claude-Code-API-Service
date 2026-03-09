"""Provider discovery commands"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from ..api_client import APIClient, APIError
from ..utils import print_error, print_section, print_success

app = typer.Typer(help="Provider and model discovery")
console = Console()


@app.command("list")
def list_providers(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List available providers"""

    try:
        client = APIClient()

        providers = client.get_providers()

        if json_output:
            print(json.dumps(providers, indent=2, default=str))
            return

        print_section("Available Providers")
        print()

        table = Table()
        table.add_column("Provider", style="cyan")
        table.add_column("Available", style="green")
        table.add_column("Models", style="white")

        for p in providers:
            name = p.get("name", "unknown")
            available = "Yes" if p.get("available") else "No"
            models = ", ".join(p.get("models", []))
            table.add_row(name, available, models)

        console.print(table)

    except APIError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command()
def models(
    provider: str = typer.Argument(..., help="Provider name (e.g. anthropic, openai)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show models for a specific provider"""

    try:
        client = APIClient()

        data = client.get_provider_models(provider)

        if json_output:
            print(json.dumps(data, indent=2, default=str))
            return

        print_section(f"Models for {provider}")
        print()

        models_list = data.get("models", [])
        if not models_list:
            print_success(f"Provider: {data.get('name', provider)}")
            console.print("  No model details available")
            return

        table = Table()
        table.add_column("Model", style="cyan")
        table.add_column("Max Tokens", style="white", justify="right")
        table.add_column("Context Window", style="white", justify="right")
        table.add_column("Vision", style="white")

        for m in models_list:
            name = m.get("name", "unknown")
            max_tokens = str(m.get("max_tokens", "N/A"))
            context = str(m.get("context_window", "N/A"))
            vision = "Yes" if m.get("supports_vision") else "No"
            table.add_row(name, max_tokens, context, vision)

        console.print(table)

    except APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
