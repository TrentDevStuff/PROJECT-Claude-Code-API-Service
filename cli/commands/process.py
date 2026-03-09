"""Process endpoint commands"""

from __future__ import annotations

import json
import time

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..api_client import APIClient, APIError
from ..utils import (
    format_cost,
    print_error,
    print_section,
    print_success,
)

app = typer.Typer(help="Process endpoint (AI Services compatible)")
console = Console()


@app.command()
def send(
    prompt: str = typer.Argument(..., help="User message to send"),
    provider: str = typer.Option("anthropic", help="Provider name (anthropic, openai, google)"),
    model: str = typer.Option("haiku", help="Model name (haiku, sonnet, opus, or provider-specific)"),
    system: str = typer.Option(None, help="System message"),
    use_cli: bool = typer.Option(False, "--use-cli", help="Use CLI execution path (slower, supports tools)"),
    max_tokens: int = typer.Option(None, help="Maximum tokens to generate"),
    project_id: str = typer.Option(None, help="Project ID for budget tracking"),
    key: str = typer.Option(None, help="API key"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Send a prompt via /v1/process"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        if not json_output:
            print_section("POST /v1/process")
            console.print(f"  Provider: {provider}")
            console.print(f"  Model: {model}")
            console.print(f"  Path: {'CLI' if use_cli else 'SDK'}")
            console.print(f'  Prompt: "{prompt[:80]}{"..." if len(prompt) > 80 else ""}"')
            print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task("Sending request...", total=None)
            start = time.time()

            try:
                response = client.process(
                    provider=provider,
                    model_name=model,
                    user_message=prompt,
                    system_message=system,
                    max_tokens=max_tokens,
                    use_cli=use_cli,
                    project_id=project_id,
                )
                duration = time.time() - start
                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Request failed: {str(e)}")
                raise typer.Exit(1)

        if json_output:
            print(json.dumps(response, indent=2, default=str))
            return

        print_success(f"Response received ({duration:.1f}s)")

        content = response.get("content", "N/A")
        console.print(f'  Content: "{content[:200]}{"..." if len(str(content)) > 200 else ""}"')

        metadata = response.get("metadata", {})
        if metadata:
            actual_model = metadata.get("actual_model", "N/A")
            mapped_from = metadata.get("mapped_from", "")
            console.print(f"  Model: {actual_model}")
            if mapped_from:
                console.print(f"  Mapping: {mapped_from}")

            usage = metadata.get("usage", {})
            if usage:
                console.print(
                    f"  Tokens: {usage.get('input_tokens', 0)} input, "
                    f"{usage.get('output_tokens', 0)} output"
                )

            cost = metadata.get("cost_usd")
            if cost is not None:
                console.print(f"  Cost: {format_cost(cost)}")

    except Exception as e:
        print_error(f"Process failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def test(
    use_cli: bool = typer.Option(False, "--use-cli", help="Test CLI execution path instead of SDK"),
    key: str = typer.Option(None, help="API key"),
):
    """Quick smoke test of /v1/process"""

    try:
        client = APIClient(api_key=key) if key else APIClient()
        path = "CLI" if use_cli else "SDK"

        print_section(f"Smoke Test: /v1/process ({path} path)")
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Testing {path} path...", total=None)
            start = time.time()

            try:
                response = client.process(
                    provider="anthropic",
                    model_name="haiku",
                    user_message="Reply with exactly: OK",
                    use_cli=use_cli,
                )
                duration = time.time() - start
                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Test failed: {str(e)}")
                raise typer.Exit(1)

        content = response.get("content", "")
        metadata = response.get("metadata", {})
        actual_model = metadata.get("actual_model", "N/A")
        cost = metadata.get("cost_usd")

        print_success(f"Response received ({duration:.1f}s)")
        print_success(f"Path: {path}")
        print_success(f"Model: {actual_model}")
        print_success(f'Content: "{content[:100]}"')
        if cost is not None:
            print_success(f"Cost: {format_cost(cost)}")

    except Exception as e:
        print_error(f"Smoke test failed: {str(e)}")
        raise typer.Exit(1)
