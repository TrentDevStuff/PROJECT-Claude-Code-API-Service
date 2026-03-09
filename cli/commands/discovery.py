"""Agent and skill discovery commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..api_client import APIClient
from ..config import ConfigManager
from ..utils import print_error

console = Console()

# Separate apps for agents and skills
agents_app = typer.Typer(help="Agent discovery and inspection")
skills_app = typer.Typer(help="Skill discovery and inspection")


def get_capabilities(api_key: str | None = None):
    """Get capabilities from API service."""
    try:
        config = ConfigManager()
        base_url = f"http://{config.load().service.host}:{config.load().service.port}"
        client = APIClient(base_url, api_key=api_key)
        return client.get_capabilities()
    except Exception as e:
        print_error(f"Failed to get capabilities: {e}")
        raise typer.Exit(1)


@agents_app.command("list")
def list_agents(
    model: str | None = typer.Option(None, help="Filter by model (haiku, sonnet, opus)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """List all available agents."""
    caps = get_capabilities(api_key=key)
    agents = caps.get("agents", [])

    # Filter by model if specified
    if model:
        model_lower = model.lower()
        agents = [agent for agent in agents if agent.get("model", "").lower() == model_lower]

    if json_output:
        console.print_json(data=agents)
        return

    # Create table
    table = Table(title=f"Available Agents ({len(agents)})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta")
    table.add_column("Tools", style="blue")

    for agent in sorted(agents, key=lambda a: a.get("name", "")):
        name = agent.get("name", "unknown")
        model_str = agent.get("model", "unknown")
        tools = agent.get("tools", [])
        tools_str = ", ".join(tools[:3])
        if len(tools) > 3:
            tools_str += f"... (+{len(tools) - 3} more)"

        table.add_row(name, model_str, tools_str)

    console.print(table)
    console.print(f"\nTotal: {len(agents)} agents")


@agents_app.command("info")
def agent_info(
    name: str = typer.Argument(..., help="Agent name to inspect"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """Show detailed information about an agent."""
    caps = get_capabilities(api_key=key)
    agents = caps.get("agents", [])

    # Find agent by name
    agent = None
    for a in agents:
        if a.get("name") == name:
            agent = a
            break

    if not agent:
        print_error(f"Agent '{name}' not found")
        # Show similar names
        similar = [a.get("name") for a in agents if name.lower() in a.get("name", "").lower()]
        if similar:
            console.print("\nDid you mean one of these?", style="yellow")
            for s in similar[:5]:
                console.print(f"  • {s}")
        raise typer.Exit(1)

    # Create formatted output
    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print("━" * 50)

    # Model
    console.print(f"[bold]Model:[/bold]        {agent.get('model', 'unknown')}")

    # Description
    desc = agent.get("description", "No description available")
    # Wrap long descriptions
    if len(desc) > 60:
        lines = []
        words = desc.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 60:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip())
        desc = "\n              ".join(lines)

    console.print(f"[bold]Description:[/bold]  {desc}")

    # Tools
    tools = agent.get("tools", [])
    if tools:
        tools_str = ", ".join(tools)
        # Wrap tools if too long
        if len(tools_str) > 60:
            # Split into multiple lines
            lines = []
            current = ""
            for i, tool in enumerate(tools):
                if i == 0:
                    current = tool
                elif len(current) + len(tool) + 2 <= 60:
                    current += ", " + tool
                else:
                    lines.append(current)
                    current = tool
            lines.append(current)
            tools_str = "\n              ".join(lines)
        console.print(f"\n[bold]Tools:[/bold]        {tools_str}")

    # Usage example
    console.print("\n[bold]How to Use:[/bold]")
    console.print("  Task(")
    console.print(f'    subagent_type="{name}",')
    console.print('    prompt="Your task description",')
    console.print('    description="Brief description"')
    console.print("  )")
    console.print()


@agents_app.command("search")
def search_agents(
    query: str = typer.Argument(..., help="Search query"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """Search agents by keyword in name or description."""
    caps = get_capabilities(api_key=key)
    agents = caps.get("agents", [])

    query_lower = query.lower()

    # Search in name and description
    matches = []
    for agent in agents:
        name = agent.get("name", "")
        desc = agent.get("description", "")
        if query_lower in name.lower() or query_lower in desc.lower():
            matches.append(agent)

    if not matches:
        console.print(f"No agents found matching '{query}'", style="yellow")
        raise typer.Exit(0)

    console.print(f"Search results for '{query}' ({len(matches)} agents):\n")

    for agent in sorted(matches, key=lambda a: a.get("name", "")):
        name = agent.get("name", "unknown")
        model = agent.get("model", "unknown")
        desc = agent.get("description", "No description")
        # Truncate long descriptions
        if len(desc) > 80:
            desc = desc[:77] + "..."

        console.print(f"  • [cyan]{name}[/cyan] ([magenta]{model}[/magenta])")
        console.print(f"    {desc}\n")


@skills_app.command("list")
def list_skills(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """List all available skills."""
    caps = get_capabilities(api_key=key)
    skills = caps.get("skills", [])

    if json_output:
        console.print_json(data=skills)
        return

    # Create table
    table = Table(title=f"Available Skills ({len(skills)})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="blue")

    for skill in sorted(skills, key=lambda s: s.get("name", "")):
        name = skill.get("name", "unknown")
        desc = skill.get("description", "No description")
        # Truncate long descriptions for table
        if len(desc) > 60:
            desc = desc[:57] + "..."

        table.add_row(name, desc)

    console.print(table)
    console.print(f"\nTotal: {len(skills)} skills")


@skills_app.command("info")
def skill_info(
    name: str = typer.Argument(..., help="Skill name to inspect"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """Show detailed information about a skill."""
    caps = get_capabilities(api_key=key)
    skills = caps.get("skills", [])

    # Find skill by name
    skill = None
    for s in skills:
        if s.get("name") == name:
            skill = s
            break

    if not skill:
        print_error(f"Skill '{name}' not found")
        # Show similar names
        similar = [s.get("name") for s in skills if name.lower() in s.get("name", "").lower()]
        if similar:
            console.print("\nDid you mean one of these?", style="yellow")
            for s in similar[:5]:
                console.print(f"  • {s}")
        raise typer.Exit(1)

    # Create formatted output
    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print("━" * 50)

    # Description
    desc = skill.get("description", "No description available")
    # Wrap long descriptions
    if len(desc) > 60:
        lines = []
        words = desc.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 60:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip())
        desc = "\n              ".join(lines)

    console.print(f"[bold]Description:[/bold]  {desc}")

    # Automation level if available
    automation = skill.get("automation_rate")
    if automation:
        console.print(f"\n[bold]Automation:[/bold]   {automation}")

    # Usage example
    console.print("\n[bold]How to Use:[/bold]")
    console.print(f'  Skill(command="{name}")')
    console.print()


@skills_app.command("search")
def search_skills(
    query: str = typer.Argument(..., help="Search query"),
    key: str | None = typer.Option(None, "--key", help="API key to use"),
):
    """Search skills by keyword in name or description."""
    caps = get_capabilities(api_key=key)
    skills = caps.get("skills", [])

    query_lower = query.lower()

    # Search in name and description
    matches = []
    for skill in skills:
        name = skill.get("name", "")
        desc = skill.get("description", "")
        if query_lower in name.lower() or query_lower in desc.lower():
            matches.append(skill)

    if not matches:
        console.print(f"No skills found matching '{query}'", style="yellow")
        raise typer.Exit(0)

    console.print(f"Search results for '{query}' ({len(matches)} skills):\n")

    for skill in sorted(matches, key=lambda s: s.get("name", "")):
        name = skill.get("name", "unknown")
        desc = skill.get("description", "No description")
        # Truncate long descriptions
        if len(desc) > 80:
            desc = desc[:77] + "..."

        console.print(f"  • [cyan]{name}[/cyan]")
        console.print(f"    {desc}\n")
