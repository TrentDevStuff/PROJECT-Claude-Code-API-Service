"""
Agent and Skill Discovery for Claude Code Integration.

Scans ~/.claude/agents/ and ~/.claude/skills/ to discover available
capabilities that can be invoked through the API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Information about a discovered agent."""

    name: str
    description: str
    tools: list[str]
    model: str
    file_path: str


@dataclass
class SkillInfo:
    """Information about a discovered skill."""

    name: str
    description: str
    command: str
    user_interface: str | None
    file_path: str


class AgentSkillDiscovery:
    """
    Discovers and caches Claude Code agents and skills.

    Provides metadata about available agents/skills to enhance
    agentic task execution with proper invocation examples.
    """

    def __init__(self, claude_dir: Path | None = None):
        """
        Initialize discovery.

        Args:
            claude_dir: Path to .claude directory (defaults to ~/.claude)
        """
        self.claude_dir = claude_dir or (Path.home() / ".claude")
        self.agents_dir = self.claude_dir / "agents"
        self.skills_dir = self.claude_dir / "skills"

        self._agents_cache: dict[str, AgentInfo] | None = None
        self._skills_cache: dict[str, SkillInfo] | None = None

    def discover_agents(self, force_refresh: bool = False) -> dict[str, AgentInfo]:
        """
        Discover all available agents.

        Args:
            force_refresh: Bypass cache and re-scan directory

        Returns:
            Dictionary mapping agent names to AgentInfo objects
        """
        if self._agents_cache is not None and not force_refresh:
            return self._agents_cache

        agents = {}

        if not self.agents_dir.exists():
            return agents

        for agent_file in self.agents_dir.glob("*.md"):
            try:
                info = self._parse_agent_file(agent_file)
                if info:
                    agents[info.name] = info
            except Exception as e:
                # Skip malformed agent files
                logger.warning("Could not parse agent %s: %s", agent_file.name, e)
                continue

        self._agents_cache = agents
        return agents

    def discover_skills(self, force_refresh: bool = False) -> dict[str, SkillInfo]:
        """
        Discover all available skills.

        Args:
            force_refresh: Bypass cache and re-scan directory

        Returns:
            Dictionary mapping skill names to SkillInfo objects
        """
        if self._skills_cache is not None and not force_refresh:
            return self._skills_cache

        skills = {}

        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_json = skill_dir / "skill.json"
            if not skill_json.exists():
                continue

            try:
                info = self._parse_skill_file(skill_dir, skill_json)
                if info:
                    skills[info.name] = info
            except Exception as e:
                # Skip malformed skill files
                logger.warning("Could not parse skill %s: %s", skill_dir.name, e)
                continue

        self._skills_cache = skills
        return skills

    def get_agent(self, name: str) -> AgentInfo | None:
        """Get specific agent by name."""
        agents = self.discover_agents()
        return agents.get(name)

    def get_skill(self, name: str) -> SkillInfo | None:
        """Get specific skill by name."""
        skills = self.discover_skills()
        return skills.get(name)

    def _parse_agent_file(self, file_path: Path) -> AgentInfo | None:
        """
        Parse agent markdown file with YAML frontmatter.

        Expected format:
        ---
        description: "Agent description"
        tools: ["Read", "Write"]
        model: "sonnet"
        ---
        # Agent content here
        """
        content = file_path.read_text()

        # Extract YAML frontmatter
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            metadata = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

        # Handle both 'tools' and 'allowed-tools' field names
        tools = metadata.get("allowed-tools") or metadata.get("tools") or []

        # Ensure tools is a list (YAML might parse as string if malformed)
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]

        return AgentInfo(
            name=file_path.stem,
            description=metadata.get("description", "No description"),
            tools=tools,
            model=metadata.get("model", "sonnet"),
            file_path=str(file_path),
        )

    def _parse_skill_file(self, skill_dir: Path, skill_json: Path) -> SkillInfo | None:
        """
        Parse skill.json metadata file.

        Expected format:
        {
          "name": "skill-name",
          "description": "Skill description",
          "command": "skill-command",
          "user_interface": {"type": "agent-wrapped"}
        }
        """
        try:
            with open(skill_json) as f:
                metadata = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        # Get user interface type
        ui_info = metadata.get("user_interface", {})
        ui_type = ui_info.get("type") if isinstance(ui_info, dict) else None

        return SkillInfo(
            name=skill_dir.name,
            description=metadata.get("description", "No description"),
            command=metadata.get("command", skill_dir.name),
            user_interface=ui_type,
            file_path=str(skill_dir),
        )

    def build_agent_prompt_section(self, allowed_agents: list[str]) -> str:
        """
        Build prompt section describing available agents.

        Args:
            allowed_agents: List of agent names allowed for this task

        Returns:
            Formatted prompt section with agent descriptions and examples
        """
        agents = self.discover_agents()
        available = [agents[name] for name in allowed_agents if name in agents]

        if not available:
            return ""

        sections = ["", "**Available Agents:**"]

        for agent in available:
            sections.append(f"- **{agent.name}**: {agent.description}")
            sections.append(f"  Model: {agent.model}")
            sections.append(f"  Tools: {', '.join(agent.tools)}")
            sections.append(
                f'  Usage: Task(subagent_type="{agent.name}", prompt="...", description="...")'
            )

        return "\n".join(sections)

    def build_skill_prompt_section(self, allowed_skills: list[str]) -> str:
        """
        Build prompt section describing available skills.

        Args:
            allowed_skills: List of skill names allowed for this task

        Returns:
            Formatted prompt section with skill descriptions and examples
        """
        skills = self.discover_skills()
        available = [skills[name] for name in allowed_skills if name in skills]

        if not available:
            return ""

        sections = ["", "**Available Skills:**"]

        for skill in available:
            # Skip agent-wrapped skills (use the agent instead)
            if skill.user_interface == "agent-wrapped":
                continue

            sections.append(f"- **{skill.name}**: {skill.description}")
            sections.append(f'  Usage: Skill(command="{skill.command}")')

        return "\n".join(sections)

    def validate_agents(self, requested: list[str]) -> dict[str, bool]:
        """
        Validate that requested agents exist.

        Args:
            requested: List of agent names to validate

        Returns:
            Dict mapping agent names to existence status
        """
        agents = self.discover_agents()
        return {name: name in agents for name in requested}

    def validate_skills(self, requested: list[str]) -> dict[str, bool]:
        """
        Validate that requested skills exist.

        Args:
            requested: List of skill names to validate

        Returns:
            Dict mapping skill names to existence status
        """
        skills = self.discover_skills()
        return {name: name in skills for name in requested}
