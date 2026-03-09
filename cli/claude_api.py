#!/usr/bin/env python3
"""Claude Code API Service CLI - Main Entry Point"""


import typer
from rich.console import Console

# Import command groups
from .commands import batch, discovery, health, keys, process, providers, route, service, tasks, test, usage, workers
from .config import config_manager
from .utils import print_error, print_info, print_success

app = typer.Typer(
    name="claude-api",
    help="Claude Code API Service CLI - Manage and monitor your API service",
    add_completion=True,
)

console = Console()

# Register command groups
app.add_typer(service.app, name="service")
app.add_typer(health.app, name="health")
app.add_typer(keys.app, name="keys")
app.add_typer(usage.app, name="usage")
app.add_typer(workers.app, name="workers")
app.add_typer(tasks.app, name="tasks")
app.add_typer(test.app, name="test")
app.add_typer(process.app, name="process")
app.add_typer(providers.app, name="providers")
app.add_typer(batch.app, name="batch")
app.add_typer(route.app, name="route")
app.add_typer(discovery.agents_app, name="agents")
app.add_typer(discovery.skills_app, name="skills")


@app.command()
def version():
    """Show CLI version"""
    from . import __version__

    print(f"claude-api version {__version__}")


@app.command()
def config_show():
    """Show current configuration"""
    try:
        config = config_manager.load()

        print_info(f"Configuration loaded from: {config_manager.config_file}")
        print()

        console.print("Service Configuration:", style="bold cyan")
        console.print(f"  Directory: {config.service.directory}")
        console.print(f"  Port: {config.service.port}")
        console.print(f"  Host: {config.service.host}")
        console.print(f"  Auto Start: {config.service.auto_start}")
        print()

        console.print("CLI Configuration:", style="bold cyan")
        console.print(f"  Default Output: {config.cli.default_output}")
        console.print(f"  Color: {config.cli.color}")
        console.print(f"  Verbose: {config.cli.verbose}")

        print()
        print_success(f"Service URL: {config_manager.get_service_url()}")

    except Exception as e:
        print_error(f"Failed to load configuration: {str(e)}")
        raise typer.Exit(1)


@app.command()
def config_validate():
    """Validate configuration and dependencies"""
    try:
        from .commands.health import deps

        deps.callback()  # Run dependency check
        print_success("Configuration validation complete")

    except Exception as e:
        print_error(f"Configuration validation failed: {str(e)}")
        raise typer.Exit(1)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
):
    """
    Claude Code API Service CLI

    Manage, monitor, and test your Claude Code API Service.
    """
    if verbose:
        config = config_manager.load()
        config.cli.verbose = True


if __name__ == "__main__":
    app()
