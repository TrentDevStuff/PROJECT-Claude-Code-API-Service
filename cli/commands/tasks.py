"""Task management commands"""

from __future__ import annotations

import typer
from rich.console import Console

from ..utils import (
    print_error,
    print_info,
    print_warning,
)

app = typer.Typer(help="Task management")
console = Console()


@app.command()
def list(
    status: str | None = typer.Option(
        None, help="Filter by status (pending, running, completed, failed)"
    ),
    limit: int = typer.Option(20, help="Number of tasks to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List active/recent tasks"""

    try:
        print_warning("Task listing endpoint not yet implemented in API")
        print_info("This feature requires API enhancement to track task history")

        console.print("\nTask management would show:", style="dim")
        console.print("  • Task ID", style="dim")
        console.print("  • Status (pending/running/completed/failed)", style="dim")
        console.print("  • Model used", style="dim")
        console.print("  • Duration", style="dim")
        console.print("  • Cost", style="dim")

    except Exception as e:
        print_error(f"Failed to list tasks: {str(e)}")
        raise typer.Exit(1)


@app.command()
def get(
    task_id: str = typer.Argument(..., help="Task ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get detailed task information"""

    try:
        # The /v1/task endpoint returns task results, but there's no GET endpoint for task details
        print_warning("Task retrieval endpoint not yet implemented in API")
        print_info(f"Task ID: {task_id}")
        print_info("This feature requires API enhancement to query task by ID")

    except Exception as e:
        print_error(f"Failed to get task: {str(e)}")
        raise typer.Exit(1)


@app.command()
def cancel(
    task_id: str = typer.Argument(..., help="Task ID to cancel"),
):
    """Cancel a running task"""

    try:
        print_warning("Task cancellation endpoint not yet implemented in API")
        print_info(f"Task ID: {task_id}")
        print_info("This feature requires API enhancement")

    except Exception as e:
        print_error(f"Failed to cancel task: {str(e)}")
        raise typer.Exit(1)


@app.command()
def logs(
    task_id: str = typer.Argument(..., help="Task ID"),
):
    """View task execution logs"""

    try:
        print_warning("Task logs endpoint not yet implemented in API")
        print_info(f"Task ID: {task_id}")
        print_info("This feature requires API enhancement to store task logs")

    except Exception as e:
        print_error(f"Failed to get task logs: {str(e)}")
        raise typer.Exit(1)
