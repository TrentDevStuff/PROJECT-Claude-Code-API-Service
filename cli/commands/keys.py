"""API key management commands"""

from __future__ import annotations

import json
import os
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

# Key store directory for persisting service keys
KEY_STORE_DIR = Path.home() / ".claude-api" / "keys"


def get_auth_manager() -> AuthManager:
    """Get AuthManager instance"""
    config = config_manager.load()
    db_path = config.service.directory / "data" / "auth.db"
    return AuthManager(db_path=str(db_path))


def get_permission_manager() -> PermissionManager:
    """Get PermissionManager instance"""
    return PermissionManager()


def _key_file_path(service_id: str) -> Path:
    """Get the key file path for a service."""
    return KEY_STORE_DIR / f"{service_id}.key"


def _save_key(service_id: str, api_key: str, project_id: str, profile: str):
    """Save a key to the local key store."""
    KEY_STORE_DIR.mkdir(parents=True, exist_ok=True)
    key_file = _key_file_path(service_id)
    key_data = {
        "key": api_key,
        "project_id": project_id,
        "profile": profile,
        "service_id": service_id,
    }
    key_file.write_text(json.dumps(key_data, indent=2) + "\n")
    key_file.chmod(0o600)


def _load_key(service_id: str) -> dict | None:
    """Load a key from the local key store. Returns None if not found."""
    key_file = _key_file_path(service_id)
    if not key_file.exists():
        return None
    try:
        return json.loads(key_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@app.command()
def create(
    project_id: str = typer.Option(..., "--project-id", "-p", help="Project identifier"),
    profile: str = typer.Option("enterprise", help="Permission profile (free, pro, enterprise)"),
    rate_limit: int = typer.Option(100, help="Requests per minute"),
    name: str | None = typer.Option(None, "--name", "-n", help="Friendly name for key"),
    save_as: str | None = typer.Option(
        None, "--save-as", "-s", help="Save to key store with this service ID"
    ),
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

        # Save to key store if requested
        if save_as:
            _save_key(save_as, api_key, project_id, profile)

        print_success("API key created successfully")
        print()

        if output_format == "json":
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

            if save_as:
                console.print(f"Saved to:    [green]{_key_file_path(save_as)}[/green]")

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
        auth_manager = get_auth_manager()
        rows = auth_manager.list_keys(project_id=project_id, active_only=active_only)

        keys = [
            {
                "api_key": row["key"],
                "project_id": row["project_id"],
                "rate_limit": row["rate_limit"],
                "created_at": row["created_at"],
                "revoked": bool(row["revoked"]),
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

        # Validate key
        is_valid, project_id = auth_manager.validate_key(key)
        if is_valid:
            print_success(f"API key is valid (project: {project_id})")
        else:
            print_error("API key is invalid or revoked")
            raise typer.Exit(1)

    except Exception as e:
        print_error(f"Failed to test key: {str(e)}")
        raise typer.Exit(1)


@app.command()
def provision(
    service_id: str = typer.Argument(..., help="Service identifier (e.g. claude-agents, playground)"),
    profile: str = typer.Option("enterprise", help="Permission profile (free, pro, enterprise)"),
    rate_limit: int = typer.Option(100, help="Requests per minute"),
    force: bool = typer.Option(False, "--force", "-f", help="Create new key even if valid one exists"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Output only the key (for scripts)"),
):
    """Get or create a persistent API key for a local service.

    Checks the local key store for an existing valid key. If found and still
    valid in the auth database, returns it. Otherwise creates a new key,
    saves it to ~/.claude-api/keys/<service-id>.key, and returns it.

    This is the recommended way for local services to obtain their API key.
    The key persists across service restarts.

    Examples:
        claude-api keys provision claude-agents
        claude-api keys provision playground --profile pro
        claude-api keys provision my-service -q  # just the key, for scripts
        CLAUDE_API_KEY=$(claude-api keys provision my-service -q)
    """
    try:
        auth_manager = get_auth_manager()

        # Check for existing stored key
        if not force:
            stored = _load_key(service_id)
            if stored:
                is_valid, _ = auth_manager.validate_key(stored["key"])
                if is_valid:
                    if quiet:
                        print(stored["key"])
                    else:
                        print_success(f"Existing key for '{service_id}' is valid")
                        console.print(f"Key:      [cyan]{stored['key']}[/cyan]")
                        console.print(f"Project:  {stored['project_id']}")
                        console.print(f"Profile:  {stored['profile']}")
                        console.print(f"Stored:   {_key_file_path(service_id)}")
                    return
                else:
                    if not quiet:
                        print_warning(f"Stored key for '{service_id}' is no longer valid, creating new one")

        # Create new key
        project_id = service_id
        perm_manager = get_permission_manager()
        api_key = auth_manager.generate_key(project_id, rate_limit=rate_limit)
        perm_manager.apply_default_profile(api_key, profile)

        # Persist to key store
        _save_key(service_id, api_key, project_id, profile)

        if quiet:
            print(api_key)
        else:
            print_success(f"Key provisioned for '{service_id}'")
            console.print(f"Key:      [cyan]{api_key}[/cyan]")
            console.print(f"Project:  {project_id}")
            console.print(f"Profile:  {profile}")
            console.print(f"Saved to: [green]{_key_file_path(service_id)}[/green]")
            print()
            print_info("Use in your service:")
            console.print(f'  CLAUDE_API_KEY=$(claude-api keys provision {service_id} -q)', style="dim")

    except Exception as e:
        print_error(f"Failed to provision key: {str(e)}")
        raise typer.Exit(1)


@app.command("get")
def get_key(
    service_id: str = typer.Argument(..., help="Service identifier"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Output only the key"),
):
    """Get a stored key for a service from the local key store.

    Returns the key saved by 'provision' or 'create --save-as'. Does NOT
    create a new key — use 'provision' for get-or-create behavior.

    Examples:
        claude-api keys get claude-agents
        CLAUDE_API_KEY=$(claude-api keys get my-service -q)
    """
    stored = _load_key(service_id)
    if not stored:
        print_error(
            f"No stored key for '{service_id}'",
            f"Run: claude-api keys provision {service_id}",
        )
        raise typer.Exit(1)

    if quiet:
        print(stored["key"])
    else:
        # Optionally check validity
        try:
            auth_manager = get_auth_manager()
            is_valid, _ = auth_manager.validate_key(stored["key"])
            status = "[green]valid[/green]" if is_valid else "[red]invalid/revoked[/red]"
        except Exception:
            status = "[yellow]unknown (service unreachable)[/yellow]"

        console.print(f"Key:      [cyan]{stored['key']}[/cyan]")
        console.print(f"Project:  {stored['project_id']}")
        console.print(f"Profile:  {stored['profile']}")
        console.print(f"Status:   {status}")
        console.print(f"Stored:   {_key_file_path(service_id)}")


@app.command("store-list")
def store_list():
    """List all keys in the local key store."""
    if not KEY_STORE_DIR.exists():
        print_warning("No keys stored yet")
        print_info("Run: claude-api keys provision <service-id>")
        return

    key_files = sorted(KEY_STORE_DIR.glob("*.key"))
    if not key_files:
        print_warning("No keys stored yet")
        return

    auth_manager = get_auth_manager()

    table = Table(title="Local Key Store")
    table.add_column("Service", style="cyan")
    table.add_column("Key", style="white")
    table.add_column("Project", style="white")
    table.add_column("Profile", style="yellow")
    table.add_column("Status", style="white")

    for kf in key_files:
        service_id = kf.stem
        data = _load_key(service_id)
        if not data:
            table.add_row(service_id, "?", "?", "?", "[red]corrupt[/red]")
            continue

        try:
            is_valid, _ = auth_manager.validate_key(data["key"])
            status = "[green]valid[/green]" if is_valid else "[red]invalid[/red]"
        except Exception:
            status = "[yellow]unknown[/yellow]"

        table.add_row(
            service_id,
            f"{data['key'][:15]}...",
            data.get("project_id", "?"),
            data.get("profile", "?"),
            status,
        )

    console.print(table)
