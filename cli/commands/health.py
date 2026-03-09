"""Health check commands"""

from pathlib import Path

import typer
from rich.console import Console

from ..api_client import APIClient, APIError
from ..utils import (
    create_status_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)

app = typer.Typer(help="Health checks")
console = Console()


@app.command()
def check(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed component status"),
):
    """Comprehensive health check using deep /health endpoint"""

    try:
        client = APIClient()

        # Get deep health data from API
        try:
            health_data = client.get_health()
            overall_status = health_data.get("status", "unknown")
        except APIError as e:
            print_error("Service not responding", str(e))
            raise typer.Exit(1)

        if json_output:
            import json

            console.print(json.dumps(health_data, indent=2))
            return

        # Overall status
        if overall_status == "ok":
            print_success("Overall: Healthy")
        else:
            print_warning(f"Overall: {overall_status.title()}")

        # Uptime
        uptime = health_data.get("uptime_seconds")
        if uptime is not None:
            from ..utils import format_duration

            print_info(f"Uptime: {format_duration(uptime)} (v{health_data.get('version', '?')})")

        print()

        # Per-service status from /health response
        components = []
        services = health_data.get("services", {})

        for svc_name, svc_data in services.items():
            svc_status = svc_data.get("status", "unknown")
            label = svc_name.replace("_", " ").title()

            if svc_status == "ok":
                detail_str = "✓ OK"
                # Show worker pool detail if verbose
                if verbose and svc_name == "worker_pool":
                    detail = svc_data.get("detail", {})
                    if detail:
                        active = detail.get("active_workers", "?")
                        max_w = detail.get("max_workers", "?")
                        queued = detail.get("queued_tasks", "?")
                        detail_str = f"✓ OK ({active}/{max_w} workers, {queued} queued)"
            elif svc_status == "unavailable":
                detail_str = "✗ Unavailable"
            else:
                detail_str = f"⚠ {svc_status}"

            components.append((label, detail_str))

        # Local-only checks (not in /health): agent/skill directories
        agents_dir = Path.home() / ".claude" / "agents"
        if agents_dir.exists():
            agent_count = len(list(agents_dir.glob("*.md")))
            components.append(("Agent Discovery", f"✓ {agent_count} agents found"))
        else:
            components.append(("Agent Discovery", "✗ Directory not found"))

        skills_dir = Path.home() / ".claude" / "skills"
        if skills_dir.exists():
            skill_count = len(list(skills_dir.glob("*/skill.json")))
            components.append(("Skill Discovery", f"✓ {skill_count} skills found"))
        else:
            components.append(("Skill Discovery", "✗ Directory not found"))

        table = create_status_table("Health Check Results", components)
        console.print(table)

    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Health check failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def deps():
    """Check dependencies only"""

    try:
        deps_status = []

        # Redis
        print_info("Checking Redis...")
        try:
            import redis

            r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
            r.ping()
            info = r.info()
            mem_used = info.get("used_memory_human", "unknown")

            deps_status.append(("Status", "✓ Running"))
            deps_status.append(("Port", "6379"))
            deps_status.append(("Memory", mem_used))
        except ImportError:
            deps_status.append(("Status", "✗ redis-py not installed"))
        except Exception as e:
            deps_status.append(("Status", "✗ Not running"))
            deps_status.append(("Error", str(e)))

        table = create_status_table("Redis (required)", deps_status)
        console.print(table)
        print()

        # Claude CLI
        claude_status = []
        print_info("Checking Claude CLI...")
        try:
            import subprocess

            result = subprocess.run(
                ["claude", "--version"], capture_output=True, check=True, timeout=5, text=True
            )
            version = result.stdout.strip()

            claude_status.append(("Installed", "✓ Yes"))
            claude_status.append(("Version", version))

            # Find path
            which_result = subprocess.run(["which", "claude"], capture_output=True, text=True)
            if which_result.returncode == 0:
                claude_status.append(("Path", which_result.stdout.strip()))

        except FileNotFoundError:
            claude_status.append(("Installed", "✗ No"))
            claude_status.append(("Install", "https://docs.anthropic.com/en/docs/claude-code"))
        except Exception as e:
            claude_status.append(("Installed", "⚠ Error"))
            claude_status.append(("Error", str(e)))

        table = create_status_table("Claude CLI (required)", claude_status)
        console.print(table)
        print()

        # Agents
        agents_status = []
        agents_dir = Path.home() / ".claude" / "agents"

        agents_status.append(("Location", str(agents_dir)))

        if agents_dir.exists():
            agent_files = list(agents_dir.glob("*.md"))
            agents_status.append(("Count", f"{len(agent_files)} discovered"))

            if agent_files:
                sample_agents = [f.stem for f in agent_files[:5]]
                agents_status.append(("Sample", ", ".join(sample_agents)))
        else:
            agents_status.append(("Status", "✗ Directory not found"))

        table = create_status_table("Agents (required)", agents_status)
        console.print(table)
        print()

        # Skills
        skills_status = []
        skills_dir = Path.home() / ".claude" / "skills"

        skills_status.append(("Location", str(skills_dir)))

        if skills_dir.exists():
            skill_dirs = [
                d for d in skills_dir.iterdir() if d.is_dir() and (d / "skill.json").exists()
            ]
            skills_status.append(("Count", f"{len(skill_dirs)} discovered"))

            if skill_dirs:
                sample_skills = [d.name for d in skill_dirs[:5]]
                skills_status.append(("Sample", ", ".join(sample_skills)))
        else:
            skills_status.append(("Status", "✗ Directory not found"))

        table = create_status_table("Skills (required)", skills_status)
        console.print(table)

    except Exception as e:
        print_error(f"Dependency check failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def ping(
    ready: bool = typer.Option(
        False, "--ready", "-r", help="Use /ready endpoint instead of /health"
    ),
):
    """Quick ping (is service responding?)"""

    try:
        client = APIClient()

        if ready:
            try:
                data = client.get_ready()
                if data.get("ready"):
                    print_success("Service is ready (accepting traffic)")
                else:
                    reason = data.get("reason", "unknown")
                    print_error(f"Service is not ready: {reason}")
                    raise typer.Exit(1)
            except APIError as e:
                print_error("Service is not responding", str(e))
                raise typer.Exit(1)
        else:
            if client.is_service_running():
                print_success("Service is responding")
            else:
                print_error("Service is not responding", "Check with: claude-api service status")
                raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Ping failed: {str(e)}")
        raise typer.Exit(1)
