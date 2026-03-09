"""Utility functions for CLI formatting and helpers"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class OutputFormatter:
    """Format output in different modes"""

    @staticmethod
    def format(data: Any, format_type: str = "table", title: str | None = None) -> None:
        """Format and print data"""
        if format_type == "json":
            print(json.dumps(data, indent=2, default=str))
        elif format_type == "text":
            print(str(data))
        else:  # table (default)
            OutputFormatter._format_table(data, title)

    @staticmethod
    def _format_table(data: Any, title: str | None = None) -> None:
        """Format data as rich table"""
        if isinstance(data, dict):
            table = Table(title=title, show_header=False)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="white")

            for key, value in data.items():
                table.add_row(str(key), str(value))

            console.print(table)

        elif isinstance(data, list) and data and isinstance(data[0], dict):
            # List of dicts - use keys as columns
            table = Table(title=title)

            keys = data[0].keys()
            for key in keys:
                table.add_column(str(key), style="cyan")

            for item in data:
                table.add_row(*[str(item.get(k, "")) for k in keys])

            console.print(table)
        else:
            console.print(data)


def print_success(message: str):
    """Print success message"""
    console.print(f"✓ {message}", style="green")


def print_error(message: str, suggestion: str | None = None):
    """Print error message with optional suggestion"""
    console.print(f"✗ {message}", style="red")
    if suggestion:
        console.print(f"  → {suggestion}", style="yellow")


def print_warning(message: str):
    """Print warning message"""
    console.print(f"⚠ {message}", style="yellow")


def print_info(message: str):
    """Print info message"""
    console.print(f"ℹ {message}", style="blue")


def print_section(title: str):
    """Print section header"""
    console.print(f"\n{title}", style="bold cyan")
    console.print("━" * len(title))


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_cost(cost: float) -> str:
    """Format cost in dollars"""
    return f"${cost:.5f}"


def format_tokens(tokens: int) -> str:
    """Format token count"""
    if tokens < 1000:
        return str(tokens)
    elif tokens < 1000000:
        return f"{tokens/1000:.1f}k"
    else:
        return f"{tokens/1000000:.1f}M"


def format_timestamp(timestamp: str) -> str:
    """Format ISO timestamp to readable format"""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp


def create_status_table(title: str, items: list[tuple]) -> Table:
    """Create a two-column status table"""
    table = Table(title=title, show_header=False)
    table.add_column("Item", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")

    for key, value in items:
        table.add_row(key, str(value))

    return table


def create_data_table(
    title: str, columns: list[str], rows: list[list[str]], column_styles: list[str] | None = None
) -> Table:
    """Create a data table with custom columns"""
    table = Table(title=title)

    styles = column_styles or ["cyan"] * len(columns)
    for col, style in zip(columns, styles):
        table.add_column(col, style=style)

    for row in rows:
        table.add_row(*row)

    return table


def spinner_context(message: str):
    """Context manager for spinner progress"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


def confirm(message: str, default: bool = False) -> bool:
    """Ask user for confirmation"""
    suffix = " [Y/n]" if default else " [y/N]"
    response = console.input(f"{message}{suffix}: ").strip().lower()

    if not response:
        return default

    return response in ("y", "yes")
