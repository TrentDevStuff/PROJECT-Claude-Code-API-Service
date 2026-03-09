"""Batch processing commands"""

from __future__ import annotations

import json
import sys
import time

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..api_client import APIClient, APIError
from ..utils import format_cost, print_error, print_section, print_success

app = typer.Typer(help="Batch processing")
console = Console()


@app.command()
def run(
    prompt: list[str] = typer.Option(None, "--prompt", "-p", help="Prompt text (repeatable)"),
    file: str = typer.Option(None, "--file", "-f", help="JSON file with prompts array"),
    model: str = typer.Option(None, help="Model for all prompts (auto-selected if omitted)"),
    timeout: float = typer.Option(30.0, help="Per-prompt timeout in seconds"),
    key: str = typer.Option(None, help="API key"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run batch of prompts via /v1/batch"""

    try:
        # Build prompts list from sources
        prompts: list[dict[str, str]] = []

        if file:
            with open(file) as f:
                data = json.load(f)
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, str):
                        prompts.append({"prompt": item, "id": f"p{i}"})
                    elif isinstance(item, dict):
                        prompts.append(item)
            else:
                print_error("File must contain a JSON array of prompts")
                raise typer.Exit(1)

        if prompt:
            for i, p in enumerate(prompt):
                prompts.append({"prompt": p, "id": f"cli{i}"})

        # Read from stdin if no other source
        if not prompts and not sys.stdin.isatty():
            stdin_data = sys.stdin.read().strip()
            try:
                data = json.loads(stdin_data)
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        if isinstance(item, str):
                            prompts.append({"prompt": item, "id": f"stdin{i}"})
                        elif isinstance(item, dict):
                            prompts.append(item)
            except json.JSONDecodeError:
                # Treat as single prompt
                prompts.append({"prompt": stdin_data, "id": "stdin0"})

        if not prompts:
            print_error("No prompts provided. Use --prompt, --file, or pipe via stdin")
            raise typer.Exit(1)

        client = APIClient(api_key=key) if key else APIClient()

        if not json_output:
            print_section(f"Batch Processing ({len(prompts)} prompts)")
            if model:
                console.print(f"  Model: {model}")
            console.print(f"  Timeout: {timeout}s per prompt")
            print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task(f"Processing {len(prompts)} prompts...", total=None)
            start = time.time()

            try:
                response = client.batch_process(
                    prompts=prompts,
                    model=model,
                    timeout=timeout,
                )
                duration = time.time() - start
                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Batch failed: {str(e)}")
                raise typer.Exit(1)

        if json_output:
            print(json.dumps(response, indent=2, default=str))
            return

        # Summary
        total = response.get("total", 0)
        completed = response.get("completed", 0)
        failed = response.get("failed", 0)
        total_cost = response.get("total_cost", 0)
        total_tokens = response.get("total_tokens", 0)

        print_success(f"Batch completed in {duration:.1f}s")
        console.print(f"  Completed: {completed}/{total}")
        if failed:
            console.print(f"  Failed: {failed}", style="red")
        console.print(f"  Total tokens: {total_tokens}")
        console.print(f"  Total cost: {format_cost(total_cost)}")
        print()

        # Results table
        results = response.get("results", [])
        if results:
            table = Table(title="Results")
            table.add_column("#", style="dim", width=4)
            table.add_column("Status", style="white", width=10)
            table.add_column("Preview", style="white")

            for i, r in enumerate(results):
                status = r.get("status", "unknown")
                style = "green" if status == "completed" else "red"
                content = r.get("content") or r.get("error") or "N/A"
                preview = content[:80] + ("..." if len(str(content)) > 80 else "")
                table.add_row(str(i + 1), f"[{style}]{status}[/{style}]", preview)

            console.print(table)

    except Exception as e:
        print_error(f"Batch processing failed: {str(e)}")
        raise typer.Exit(1)
