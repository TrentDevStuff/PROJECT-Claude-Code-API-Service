"""API key management commands"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.auth import AuthManager
from src.permission_manager import PermissionManager

from ..config import config_manager
from ..utils import (
    print_error,
    print_info,
    print_section,
    print_success,
    print_warning,
)

app = typer.Typer(help="API key management")
console = Console()


def get_auth_manager() -> AuthManager:
    """Get AuthManager instance"""
    config = config_manager.load()
    db_path = config.service.directory / "data" / "auth.db"
    return AuthManager(db_path=str(db_path))


def get_permission_manager() -> PermissionManager:
    """Get PermissionManager instance"""
    return PermissionManager()


@app.command()
def create(
    project_id: str = typer.Option(..., "--project-id", "-p", help="Project identifier"),
    profile: str = typer.Option("enterprise", help="Permission profile (free, pro, enterprise)"),
    rate_limit: int = typer.Option(100, help="Requests per minute"),
    name: str | None = typer.Option(None, "--name", "-n", help="Friendly name for key"),
    output_format: str = typer.Option(
        "text", "--output", "-o", help="Output format (text, json, env)"
    ),
):
    """Create new API key"""

    try:
        auth_manager = get_auth_manager()
        perm_manager = get_permission_manager()

        # Generate key
        api_key = auth_manager.generate_key(project_id, rate_limit=rate_limit)

        # Apply permission profile
        perm_manager.apply_default_profile(api_key, profile)

        print_success("API key created successfully")
        print()

        if output_format == "json":
            import json

            data = {
                "key": api_key,
                "project_id": project_id,
                "profile": profile,
                "rate_limit": rate_limit,
            }
            print(json.dumps(data, indent=2))

        elif output_format == "env":
            print(f"CLAUDE_API_KEY={api_key}")
            print(f"CLAUDE_API_PROJECT={project_id}")

        else:  # text
            console.print(f"Key:         [cyan]{api_key}[/cyan]")
            console.print(f"Project:     {project_id}")
            console.print(f"Profile:     {profile}")
            console.print(f"Rate Limit:  {rate_limit} req/min")

            if profile == "enterprise":
                print()
                print_info("Permissions:")
                console.print("  Tools:     All (Read, Write, Bash, Grep, Glob, etc.)")
                console.print("  Agents:    All")
                console.print("  Skills:    All")
                console.print("  Max Cost:  $10.00/task")

            print()
            print_section("Add to .env:")
            console.print(f"  CLAUDE_API_KEY={api_key}", style="dim")

    except Exception as e:
        print_error(f"Failed to create API key: {str(e)}")
        raise typer.Exit(1)


@app.command()
def list(
    project_id: str | None = typer.Option(None, "--project-id", "-p", help="Filter by project"),
    active_only: bool = typer.Option(False, help="Show only active keys"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all API keys"""

    try:
        get_auth_manager()  # validate auth is accessible

        # Query database directly (AuthManager doesn't have list_keys)
        import sqlite3

        config = config_manager.load()
        db_path = config.service.directory / "data" / "auth.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        query = "SELECT key, project_id, rate_limit, created_at, revoked FROM api_keys"
        params = []

        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)

        if active_only:
            if project_id:
                query += " AND revoked = 0"
            else:
                query += " WHERE revoked = 0"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        keys = [
            {
                "api_key": row[0],
                "project_id": row[1],
                "rate_limit": row[2],
                "created_at": row[3],
                "revoked": bool(row[4]),
            }
            for row in rows
        ]

        if not keys:
            print_warning("No API keys found")
            return

        if json_output:
            import json

            print(json.dumps(keys, indent=2, default=str))
        else:
            # Create table
            table = Table(title="API Keys")
            table.add_column("Key", style="cyan")
            table.add_column("Project", style="white")
            table.add_column("Rate Limit", style="yellow")
            table.add_column("Created", style="dim")

            for key_data in keys:
                # Truncate key for display
                key_display = f"{key_data['api_key'][:15]}..."

                table.add_row(
                    key_display,
                    key_data.get("project_id", "N/A"),
                    f"{key_data.get('rate_limit', 'N/A')}/min",
                    str(key_data.get("created_at", "N/A"))[:19],
                )

            console.print(table)
            print()
            print_info(f"Total: {len(keys)} keys")

    except Exception as e:
        print_error(f"Failed to list keys: {str(e)}")
        raise typer.Exit(1)


@app.command()
def revoke(
    key: str = typer.Argument(..., help="API key to revoke (or prefix)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Revoke an API key"""

    try:
        auth_manager = get_auth_manager()

        # Confirm unless force
        if not force:
            from ..utils import confirm

            if not confirm(f"Revoke API key {key[:15]}...?", default=False):
                print_info("Cancelled")
                return

        # Revoke key
        success = auth_manager.revoke_key(key)

        if success:
            print_success(f"API key {key[:15]}... revoked")
        else:
            print_error("Failed to revoke key", "Key may not exist")
            raise typer.Exit(1)

    except Exception as e:
        print_error(f"Failed to revoke key: {str(e)}")
        raise typer.Exit(1)


@app.command()
def permissions(
    key: str = typer.Argument(..., help="API key to inspect"),
    set_profile: str | None = typer.Option(None, help="Change profile (free, pro, enterprise)"),
    max_cost: float | None = typer.Option(None, help="Set max cost per task"),
):
    """View/set permissions for a key"""

    try:
        perm_manager = get_permission_manager()

        if set_profile:
            # Apply new profile
            perm_manager.apply_default_profile(key, set_profile)
            print_success(f"Profile updated to: {set_profile}")
            print()

        if max_cost is not None:
            # Update max cost
            profile = perm_manager.get_profile(key)
            if profile:
                profile["max_cost_per_task"] = max_cost
                perm_manager.set_profile(key, profile)
                print_success(f"Max cost updated to: ${max_cost:.2f}")
                print()

        # Show current permissions
        profile = perm_manager.get_profile(key)

        if not profile:
            print_warning("No permissions set for this key (using defaults)")
            return

        print_section(f"Permissions for {key[:15]}...")

        console.print(f"Profile:     [cyan]{profile.get('tier', 'custom')}[/cyan]")
        console.print(f"Max Cost:    ${profile.get('max_cost_per_task', 0):.2f}/task")
        print()

        # Tools
        allowed_tools = profile.get("allowed_tools", [])
        blocked_tools = profile.get("blocked_tools", [])

        if allowed_tools == ["*"]:
            console.print("Allowed Tools: [green](all)[/green]")
        elif allowed_tools:
            console.print(f"Allowed Tools: {', '.join(allowed_tools)}")

        if blocked_tools:
            console.print(f"Blocked Tools: {', '.join(blocked_tools)}", style="red")

        print()

        # Agents
        allowed_agents = profile.get("allowed_agents", [])
        if allowed_agents == ["*"]:
            console.print("Allowed Agents: [green](all)[/green]")
        elif allowed_agents:
            console.print(f"Allowed Agents: {', '.join(allowed_agents)}")

        print()

        # Skills
        allowed_skills = profile.get("allowed_skills", [])
        if allowed_skills == ["*"]:
            console.print("Allowed Skills: [green](all)[/green]")
        elif allowed_skills:
            console.print(f"Allowed Skills: {', '.join(allowed_skills)}")

    except Exception as e:
        print_error(f"Failed to get permissions: {str(e)}")
        raise typer.Exit(1)


@app.command()
def test(
    key: str = typer.Argument(..., help="API key to test"),
):
    """Test if a key is valid"""

    try:
        auth_manager = get_auth_manager()

        # Verify key
        if auth_manager.verify_key(key):
            print_success("API key is valid")
        else:
            print_error("API key is invalid or revoked")
            raise typer.Exit(1)

    except Exception as e:
        print_error(f"Failed to test key: {str(e)}")
        raise typer.Exit(1)
