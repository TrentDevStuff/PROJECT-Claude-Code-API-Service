"""Worker pool management commands"""

import typer
from rich.console import Console

from ..api_client import APIClient, APIError
from ..utils import (
    create_status_table,
    print_error,
    print_info,
    print_warning,
)

app = typer.Typer(help="Worker pool management")
console = Console()


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Worker pool status (from /health endpoint)"""

    try:
        client = APIClient()
        health_data = client.get_health()

        worker_svc = health_data.get("services", {}).get("worker_pool", {})
        worker_status = worker_svc.get("status", "unknown")
        detail = worker_svc.get("detail", {})

        if json_output:
            import json

            console.print(json.dumps({"status": worker_status, **detail}, indent=2))
            return

        if worker_status != "ok":
            print_error(f"Worker pool status: {worker_status}")
            raise typer.Exit(1)

        active = detail.get("active_workers", "?")
        max_w = detail.get("max_workers", "?")
        queued = detail.get("queued_tasks", "?")
        running = detail.get("running", False)

        items = [
            ("Status", "✓ Running" if running else "✗ Stopped"),
            ("Active Workers", f"{active} / {max_w}"),
            ("Queued Tasks", str(queued)),
        ]

        table = create_status_table("Worker Pool", items)
        console.print(table)

    except APIError as e:
        print_error(f"Failed to get worker status: {str(e)}")
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Failed to get worker status: {str(e)}")
        raise typer.Exit(1)


@app.command(name="list")
def list_workers(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List active workers"""
    print_warning("Requires /v1/workers API endpoint (not yet implemented)")
    print_info("Use 'workers status' for pool-level metrics from /health")


@app.command()
def clear_queue():
    """Clear pending tasks queue"""
    print_warning("Requires /v1/workers/queue API endpoint (not yet implemented)")
    print_info("Use 'workers status' to check current queue depth")


@app.command()
def kill(
    worker_id: int = typer.Argument(..., help="Worker ID to kill"),
):
    """Kill a specific worker"""
    print_warning("Requires /v1/workers/{id} API endpoint (not yet implemented)")
    print_info("Use 'service stop' to stop all workers gracefully")
