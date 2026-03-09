"""Service lifecycle management commands"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil
import typer
from rich.console import Console

from ..config import config_manager
from ..utils import (
    create_status_table,
    format_duration,
    print_error,
    print_info,
    print_success,
    print_warning,
)

app = typer.Typer(help="Service lifecycle management")
console = Console()

PID_FILE = Path.home() / ".claude-api" / "service.pid"
LOG_FILE = Path.home() / ".claude-api" / "service.log"
PLIST_LABEL = "com.claude-api.service"
PLIST_FILE = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def get_service_pid() -> int | None:
    """Get running service PID from file"""
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process is actually running
        if psutil.pid_exists(pid):
            return pid
        else:
            # Clean up stale PID file
            PID_FILE.unlink()
            return None
    except Exception:
        return None


def save_service_pid(pid: int):
    """Save service PID to file"""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def remove_service_pid():
    """Remove PID file"""
    if PID_FILE.exists():
        PID_FILE.unlink()


@app.command()
def start(
    port: int | None = typer.Option(None, help="Override port"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
    no_deps_check: bool = typer.Option(False, help="Skip dependency checks"),
    logs: bool = typer.Option(False, "--logs", "-l", help="Tail logs after starting"),
):
    """Start the API service"""

    try:
        config = config_manager.load()
        service_dir = config.service.directory
        service_port = port or config.service.port

        # Check if already running
        pid = get_service_pid()
        if pid:
            print_warning(f"Service already running (PID: {pid})")
            print_info(f"Service URL: http://localhost:{service_port}")
            return

        # Dependency checks
        if not no_deps_check:
            print_info("Checking dependencies...")

            # Check Redis
            try:
                import redis

                r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
                r.ping()
                print_success("Redis: running")
            except Exception:
                print_warning("Redis: not running (optional for basic usage)")

            # Check Claude CLI
            try:
                subprocess.run(["claude", "--version"], capture_output=True, check=True, timeout=5)
                print_success("Claude CLI: installed")
            except Exception:
                print_error(
                    "Claude CLI: not found",
                    "Install from: https://docs.anthropic.com/en/docs/claude-code",
                )
                raise typer.Exit(1)

            # Check agents/skills
            agents_dir = Path.home() / ".claude" / "agents"
            skills_dir = Path.home() / ".claude" / "skills"

            if agents_dir.exists():
                agent_count = len(list(agents_dir.glob("*.md")))
                print_success(f"Agents: {agent_count} discovered")
            else:
                print_warning("Agents directory not found")

            if skills_dir.exists():
                skill_count = len(list(skills_dir.glob("*/skill.json")))
                print_success(f"Skills: {skill_count} discovered")
            else:
                print_warning("Skills directory not found")

        # Check port availability
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("localhost", service_port))
        sock.close()

        if result == 0:
            print_error(f"Port {service_port} already in use")
            raise typer.Exit(1)

        print_success(f"Port {service_port} available")

        # Start service
        print_info(f"Starting Claude Code API Service on port {service_port}...")

        cmd = ["python", str(service_dir / "main.py")]
        env = os.environ.copy()
        env["CLAUDE_API_PORT"] = str(service_port)

        if background:
            # Redirect stderr (structured JSON logs) to log file
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log_fh = open(LOG_FILE, "a")

            process = subprocess.Popen(
                cmd,
                cwd=service_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=log_fh,
                start_new_session=True,
            )

            # Poll /ready for up to 5 seconds
            from ..api_client import APIClient as _AC

            ready_client = _AC(base_url=f"http://localhost:{service_port}")
            ready = False
            for _ in range(10):
                time.sleep(0.5)
                if process.poll() is not None:
                    break
                try:
                    data = ready_client.get_ready()
                    if data.get("ready"):
                        ready = True
                        break
                except Exception:
                    continue

            if process.poll() is not None:
                print_error("Service failed to start (check logs: claude-api service logs)")
                raise typer.Exit(1)

            save_service_pid(process.pid)
            if ready:
                print_success(f"Service ready (PID: {process.pid})")
            else:
                print_warning(f"Service started but not yet ready (PID: {process.pid})")
            print_success(f"Service URL: http://localhost:{service_port}")
            print_success(f"API Docs: http://localhost:{service_port}/docs")
            print_info(f"Logs: {LOG_FILE}")

            if logs:
                print_info("Tailing logs... (Ctrl+C to stop)")
                _tail_logs(follow=True)

        else:
            # Foreground: human-readable logs
            env["CLAUDE_API_LOG_JSON"] = "false"
            print_info("Service running in foreground (Ctrl+C to stop)")
            try:
                subprocess.run(cmd, cwd=service_dir, env=env)
            except KeyboardInterrupt:
                print_info("\nStopping service...")
                remove_service_pid()

    except Exception as e:
        print_error(f"Failed to start service: {str(e)}")
        raise typer.Exit(1)


@app.command()
def stop(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force kill if graceful shutdown fails"
    ),
    timeout: int = typer.Option(30, help="Shutdown timeout in seconds"),
):
    """Stop the running service"""

    try:
        pid = get_service_pid()

        if not pid:
            print_warning("Service is not running")
            return

        print_success(f"Found service (PID: {pid})")

        try:
            process = psutil.Process(pid)

            # Try graceful shutdown first
            print_info("Sending shutdown signal...")
            process.terminate()

            # Wait for process to exit
            print_info(f"Waiting for graceful shutdown (timeout: {timeout}s)...")
            process.wait(timeout=timeout)

            print_success("Service stopped successfully")
            remove_service_pid()

        except psutil.TimeoutExpired:
            if force:
                print_warning("Graceful shutdown timed out, force killing...")
                process.kill()
                process.wait(timeout=5)
                print_success("Service force-killed")
                remove_service_pid()
            else:
                print_error("Graceful shutdown timed out", "Use --force to force kill")
                raise typer.Exit(1)

        except psutil.NoSuchProcess:
            print_warning("Process already stopped")
            remove_service_pid()

    except Exception as e:
        print_error(f"Failed to stop service: {str(e)}")
        raise typer.Exit(1)


@app.command()
def restart(
    port: int | None = typer.Option(None, help="Override port"),
):
    """Restart the service"""
    print_info("Restarting service...")

    # Stop if running
    pid = get_service_pid()
    if pid:
        stop.callback(force=False, timeout=30)
        time.sleep(2)

    # Start
    start.callback(port=port, background=True, no_deps_check=True, logs=False)


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check service status"""

    try:
        from ..api_client import APIClient

        config = config_manager.load()
        client = APIClient()

        pid = get_service_pid()
        running = pid is not None

        if not running:
            print_error("Service is not running", "Start with: claude-api service start")
            raise typer.Exit(1)

        # Get process info
        process = psutil.Process(pid)

        # Get service health
        try:
            health = client.get_health()
        except Exception:
            health = None

        # Prefer server-reported uptime, fall back to OS process time
        if health and health.get("uptime_seconds") is not None:
            uptime = health["uptime_seconds"]
        else:
            uptime = time.time() - process.create_time()

        overall_status = health.get("status", "unknown") if health else "unreachable"

        # Build status table
        items = [
            ("Running", "✓ Yes"),
            ("PID", str(pid)),
            ("Port", str(config.service.port)),
            ("Uptime", format_duration(uptime)),
            ("Memory", f"{process.memory_info().rss / 1024 / 1024:.1f} MB"),
            ("CPU", f"{process.cpu_percent(interval=0.1):.1f}%"),
        ]

        if overall_status == "ok":
            items.append(("Health", "✓ OK"))
        elif overall_status == "degraded":
            items.append(("Health", "⚠ Degraded"))
        else:
            items.append(("Health", f"✗ {overall_status.title()}"))

        table = create_status_table("Service Status", items)
        console.print(table)

        # Show per-service status from /health
        if health:
            services = health.get("services", {})
            print()
            svc_items = []
            for svc_name, svc_data in services.items():
                svc_status = svc_data.get("status", "unknown")
                label = svc_name.replace("_", " ").title()
                if svc_status == "ok":
                    svc_items.append((label, "✓ OK"))
                elif svc_status == "unavailable":
                    svc_items.append((label, "✗ Unavailable"))
                else:
                    svc_items.append((label, f"⚠ {svc_status}"))

            svc_table = create_status_table("Services", svc_items)
            console.print(svc_table)

            # Worker pool detail
            wp = services.get("worker_pool", {})
            wp_detail = wp.get("detail", {})
            if wp_detail:
                print()
                wp_items = [
                    (
                        "Active Workers",
                        f"{wp_detail.get('active_workers', '?')} / {wp_detail.get('max_workers', '?')}",
                    ),
                    ("Queued Tasks", str(wp_detail.get("queued_tasks", "?"))),
                ]
                wp_table = create_status_table("Worker Pool", wp_items)
                console.print(wp_table)

    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Failed to get status: {str(e)}")
        raise typer.Exit(1)


def _build_plist(service_dir: Path, port: int) -> dict:
    """Build a launchd plist dict for the API service."""
    python_path = shutil.which("python3") or shutil.which("python") or sys.executable
    log_dir = Path.home() / ".claude-api"

    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": [python_path, str(service_dir / "main.py")],
        "WorkingDirectory": str(service_dir),
        "EnvironmentVariables": {
            "CLAUDE_API_PORT": str(port),
            "CLAUDE_API_LOG_JSON": "true",
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(Path.home()),
        },
        "KeepAlive": {"SuccessfulExit": False},  # Restart on crash, not on clean exit
        "StandardOutPath": str(log_dir / "launchd-stdout.log"),
        "StandardErrorPath": str(log_dir / "service.log"),
        "RunAtLoad": False,
        "ThrottleInterval": 5,  # Wait 5s between restart attempts
    }


@app.command()
def install(
    port: int | None = typer.Option(None, help="Override port"),
    start_now: bool = typer.Option(False, "--start", "-s", help="Load and start immediately"),
):
    """Install launchd service for auto-restart on crash (macOS)"""
    try:
        config = config_manager.load()
        service_dir = config.service.directory
        service_port = port or config.service.port

        if not service_dir.exists() or not (service_dir / "main.py").exists():
            print_error(f"Service directory not found: {service_dir}")
            raise typer.Exit(1)

        # Build plist
        plist = _build_plist(service_dir, service_port)

        # Ensure directories exist
        PLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        (Path.home() / ".claude-api").mkdir(parents=True, exist_ok=True)

        # Unload existing if present
        if PLIST_FILE.exists():
            subprocess.run(
                ["launchctl", "unload", str(PLIST_FILE)],
                capture_output=True,
            )

        # Write plist
        with open(PLIST_FILE, "wb") as f:
            plistlib.dump(plist, f)

        print_success(f"Plist installed: {PLIST_FILE}")
        print_info(f"  Working directory: {service_dir}")
        print_info(f"  Port: {service_port}")
        print_info(f"  Logs: {plist['StandardErrorPath']}")
        print_info("  Auto-restart: on crash (KeepAlive.SuccessfulExit = false)")

        if start_now:
            subprocess.run(["launchctl", "load", str(PLIST_FILE)], check=True)
            print_success("Service loaded and starting via launchd")
            print_info("Check status with: claude-api service status")
        else:
            print_info(
                "Load with: launchctl load ~/Library/LaunchAgents/com.claude-api.service.plist"
            )
            print_info("Or re-run with: claude-api service install --start")

    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Failed to install service: {str(e)}")
        raise typer.Exit(1)


@app.command()
def uninstall():
    """Remove launchd service"""
    try:
        if not PLIST_FILE.exists():
            print_warning("Launchd service not installed")
            return

        # Unload first
        result = subprocess.run(
            ["launchctl", "unload", str(PLIST_FILE)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print_success("Service unloaded from launchd")
        else:
            print_info("Service was not loaded (already stopped)")

        # Remove plist
        PLIST_FILE.unlink()
        print_success(f"Plist removed: {PLIST_FILE}")

    except Exception as e:
        print_error(f"Failed to uninstall service: {str(e)}")
        raise typer.Exit(1)


def _tail_logs(
    lines: int = 50, follow: bool = False, level: str | None = None, search: str | None = None
):
    """Read structured JSON logs from the service log file"""

    if not LOG_FILE.exists():
        print_warning(f"No log file found at {LOG_FILE}")
        print_info("Start in background mode to generate logs: claude-api service start -b")
        return

    if follow:
        # Use tail -f subprocess
        cmd = ["tail", "-f", str(LOG_FILE)]
        if not level and not search:
            try:
                subprocess.run(cmd)
            except KeyboardInterrupt:
                pass
            return

        # With filtering, read line by line
        cmd = ["tail", "-f", "-n", str(lines), str(LOG_FILE)]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
            for raw_line in proc.stdout:
                if _matches_filter(raw_line, level, search):
                    console.print(raw_line.rstrip())
        except KeyboardInterrupt:
            proc.terminate()
        return

    # Non-follow: read last N lines
    try:
        all_lines = LOG_FILE.read_text().splitlines()
    except Exception as e:
        print_error(f"Failed to read log file: {e}")
        return

    tail = all_lines[-lines:] if len(all_lines) > lines else all_lines

    for raw_line in tail:
        if _matches_filter(raw_line, level, search):
            console.print(raw_line)


def _matches_filter(raw_line: str, level: str | None, search: str | None) -> bool:
    """Check if a log line matches level/search filters"""
    import json as _json

    if not level and not search:
        return True

    # Try to parse as JSON for level filtering
    if level:
        try:
            entry = _json.loads(raw_line)
            if entry.get("level", "").upper() != level.upper():
                return False
        except (ValueError, KeyError):
            # Not JSON — match on raw text
            if level.upper() not in raw_line.upper():
                return False

    return not (search and search.lower() not in raw_line.lower())


@app.command()
def logs(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs (tail -f style)"),
    level: str | None = typer.Option(
        None, "--level", help="Filter by level (DEBUG, INFO, WARNING, ERROR)"
    ),
    search: str | None = typer.Option(None, help="Search for pattern"),
):
    """Tail service logs"""
    _tail_logs(lines=lines, follow=follow, level=level, search=search)
