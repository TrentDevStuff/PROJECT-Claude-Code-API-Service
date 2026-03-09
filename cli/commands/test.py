"""Testing commands"""

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..api_client import APIClient, APIError
from ..utils import (
    format_cost,
    format_duration,
    print_error,
    print_section,
    print_success,
    print_warning,
)

app = typer.Typer(help="Testing commands")
console = Console()


@app.command()
def completion(
    model: str = typer.Option("haiku", help="Model to test (haiku, sonnet, opus)"),
    prompt: str = typer.Option("Hello!", help="Custom prompt"),
    key: str = typer.Option(None, help="API key to use (uses test key if not provided)"),
):
    """Quick test of chat completion endpoint"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        print_section("Testing Chat Completion Endpoint")
        console.print("  POST /v1/chat/completions")
        console.print(f"  Model: {model}")
        console.print(f'  Prompt: "{prompt}"')
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Sending request...", total=None)

            import time

            start = time.time()

            try:
                response = client.chat_completion(
                    model=model, messages=[{"role": "user", "content": prompt}]
                )
                duration = time.time() - start

                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Request failed: {str(e)}")
                raise typer.Exit(1)

        print_success(f"Response received ({duration:.1f}s)")
        print_success("Status: 200 OK")

        content = response.get(
            "content", response.get("choices", [{}])[0].get("message", {}).get("content", "N/A")
        )
        console.print(f"✓ Content: \"{content[:100]}{'...' if len(str(content)) > 100 else ''}\"")

        usage = response.get("usage", {})
        if usage:
            console.print(
                f"✓ Tokens: {usage.get('input_tokens', 0)} input, {usage.get('output_tokens', 0)} output"
            )
            if "cost" in usage:
                console.print(f"✓ Cost: {format_cost(usage['cost'])}")

    except Exception as e:
        print_error(f"Test failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def task(
    description: str = typer.Option("List Python files in src/", help="Task description"),
    tools: str = typer.Option("Bash,Glob", help="Allowed tools (comma-separated)"),
    key: str = typer.Option(None, help="API key to use"),
):
    """Test agentic task endpoint"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        tool_list = [t.strip() for t in tools.split(",")]

        print_section("Testing Agentic Task Endpoint")
        console.print("  POST /v1/task")
        console.print(f'  Description: "{description}"')
        console.print(f"  Tools: {tool_list}")
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_progress = progress.add_task("Creating task...", total=None)

            import time

            start = time.time()

            try:
                response = client.create_task(
                    description=description, allow_tools=tool_list, timeout=90
                )
                time.time() - start  # elapsed, used for future display

                progress.update(task_progress, description="Task completed", completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Task failed: {str(e)}")
                raise typer.Exit(1)

        task_id = response.get("task_id", "N/A")
        status = response.get("status", "N/A")

        print_success(f"Task created (task_id: {task_id[:16]}...)")
        print_success(f"Status: {status}")

        if status == "completed":
            result = response.get("result", {})
            summary = result.get("summary", "N/A")
            console.print(f"✓ Result: {summary[:100]}{'...' if len(str(summary)) > 100 else ''}")

            usage = response.get("usage", {})
            if usage:
                console.print(f"✓ Duration: {format_duration(usage.get('duration_seconds', 0))}")
                console.print(f"✓ Cost: {format_cost(usage.get('total_cost', 0))}")

    except Exception as e:
        print_error(f"Test failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def agents(
    key: str = typer.Option(None, help="API key to use"),
):
    """Test agent discovery"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        print_section("Testing Agent Discovery")
        console.print("  GET /v1/capabilities")
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching capabilities...", total=None)

            try:
                response = client.get_capabilities()
                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Request failed: {str(e)}")
                raise typer.Exit(1)

        agents = response.get("agents", [])
        agent_count = len(agents)

        print_success(f"Found {agent_count} agents")

        if agents:
            console.print("\nSample agents:")
            for agent in agents[:5]:
                name = agent.get("name", "unknown")
                model = agent.get("model", "unknown")
                console.print(f"  • {name} ({model})", style="cyan")

        print()
        print_success("Agent discovery working correctly")

    except Exception as e:
        print_error(f"Test failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def skills(
    key: str = typer.Option(None, help="API key to use"),
):
    """Test skill discovery"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        print_section("Testing Skill Discovery")
        console.print("  GET /v1/capabilities")
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching capabilities...", total=None)

            try:
                response = client.get_capabilities()
                progress.update(task, completed=True)

            except APIError as e:
                progress.stop()
                print_error(f"Request failed: {str(e)}")
                raise typer.Exit(1)

        skills = response.get("skills", [])
        skill_count = len(skills)

        print_success(f"Found {skill_count} skills")

        if skills:
            console.print("\nSample skills:")
            for skill in skills[:5]:
                name = skill.get("name", "unknown")
                console.print(f"  • {name}", style="cyan")

        print()
        print_success("Skill discovery working correctly")

    except Exception as e:
        print_error(f"Test failed: {str(e)}")
        raise typer.Exit(1)


@app.command("process")
def process_test(
    use_cli: bool = typer.Option(False, "--use-cli", help="Test CLI path instead of SDK"),
    key: str = typer.Option(None, help="API key to use"),
):
    """Test /v1/process endpoint"""

    try:
        client = APIClient(api_key=key) if key else APIClient()
        path = "CLI" if use_cli else "SDK"

        print_section(f"Testing Process Endpoint ({path} path)")
        console.print("  POST /v1/process")
        console.print(f"  Model: haiku via anthropic")
        console.print(f"  Execution: {path}")
        print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Sending request...", total=None)

            import time

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
                print_error(f"Request failed: {str(e)}")
                raise typer.Exit(1)

        print_success(f"Response received ({duration:.1f}s)")

        content = response.get("content", "N/A")
        console.print(f'✓ Content: "{content[:100]}"')

        metadata = response.get("metadata", {})
        if metadata:
            mapped_from = metadata.get("mapped_from", "")
            if mapped_from:
                console.print(f"✓ Mapping: {mapped_from}")

            usage = metadata.get("usage", {})
            if usage:
                console.print(
                    f"✓ Tokens: {usage.get('input_tokens', 0)} input, "
                    f"{usage.get('output_tokens', 0)} output"
                )

            cost = metadata.get("cost_usd")
            if cost is not None:
                console.print(f"✓ Cost: {format_cost(cost)}")

    except Exception as e:
        print_error(f"Test failed: {str(e)}")
        raise typer.Exit(1)


@app.command()
def all(
    key: str = typer.Option(None, help="API key to use"),
):
    """Run all endpoint tests"""

    try:
        client = APIClient(api_key=key) if key else APIClient()

        results = {"passed": 0, "failed": 0, "tests": []}

        print_section("Running All Endpoint Tests")
        print()

        # Test 1: Health
        try:
            client.get_health()
            print_success("GET /health")
            results["passed"] += 1
            results["tests"].append(("GET /health", True, None))
        except Exception as e:
            print_error(f"GET /health - {str(e)}")
            results["failed"] += 1
            results["tests"].append(("GET /health", False, str(e)))

        # Test 2: Ready
        try:
            ready_data = client.get_ready()
            if ready_data.get("ready"):
                print_success("GET /ready")
            else:
                reason = ready_data.get("reason", "unknown")
                print_warning(f"GET /ready - not ready: {reason}")
            results["passed"] += 1
            results["tests"].append(("GET /ready", True, None))
        except Exception as e:
            print_error(f"GET /ready - {str(e)}")
            results["failed"] += 1
            results["tests"].append(("GET /ready", False, str(e)))

        # Test 3: Capabilities
        try:
            client.get_capabilities()
            print_success("GET /v1/capabilities")
            results["passed"] += 1
            results["tests"].append(("GET /v1/capabilities", True, None))
        except Exception as e:
            print_error(f"GET /v1/capabilities - {str(e)}")
            results["failed"] += 1
            results["tests"].append(("GET /v1/capabilities", False, str(e)))

        # Test 4: Chat completion
        try:
            client.chat_completion("haiku", [{"role": "user", "content": "Test"}])
            print_success("POST /v1/chat/completions")
            results["passed"] += 1
            results["tests"].append(("POST /v1/chat/completions", True, None))
        except Exception as e:
            print_error(f"POST /v1/chat/completions - {str(e)}")
            results["failed"] += 1
            results["tests"].append(("POST /v1/chat/completions", False, str(e)))

        # Test 5: Process
        try:
            client.process(
                provider="anthropic",
                model_name="haiku",
                user_message="Test",
            )
            print_success("POST /v1/process")
            results["passed"] += 1
            results["tests"].append(("POST /v1/process", True, None))
        except Exception as e:
            print_error(f"POST /v1/process - {str(e)}")
            results["failed"] += 1
            results["tests"].append(("POST /v1/process", False, str(e)))

        # Summary
        print()
        print_section("Test Results")
        total = results["passed"] + results["failed"]
        percentage = (results["passed"] / total * 100) if total > 0 else 0

        console.print(f"Results: {results['passed']}/{total} passed ({percentage:.1f}%)")

        if results["failed"] > 0:
            print()
            print_warning("Some tests failed - check API service status")
            raise typer.Exit(1)
        else:
            print()
            print_success("All tests passed!")

    except Exception as e:
        print_error(f"Test suite failed: {str(e)}")
        raise typer.Exit(1)
