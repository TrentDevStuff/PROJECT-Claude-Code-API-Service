"""
Tests for agent and skill discovery.
"""

import json

import pytest

from src.agent_discovery import AgentSkillDiscovery


@pytest.fixture
def test_claude_dir(tmp_path):
    """Create temporary .claude directory structure."""
    claude_dir = tmp_path / ".claude"
    agents_dir = claude_dir / "agents"
    skills_dir = claude_dir / "skills"

    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)

    # Create test agent
    (agents_dir / "test-agent.md").write_text(
        """---
description: "Test agent for testing"
tools: ["Read", "Write"]
model: "sonnet"
---

# Test Agent

This is a test agent.
"""
    )

    # Create test skill
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "test-skill",
                "description": "Test skill for testing",
                "command": "test-skill",
                "user_interface": None,
            }
        )
    )

    # Create agent-wrapped skill
    wrapped_skill_dir = skills_dir / "wrapped-skill"
    wrapped_skill_dir.mkdir()
    (wrapped_skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "wrapped-skill",
                "description": "Wrapped skill",
                "command": "wrapped-skill",
                "user_interface": {"type": "agent-wrapped"},
            }
        )
    )

    return claude_dir


class TestAgentSkillDiscovery:
    """Tests for AgentSkillDiscovery class."""

    def test_discover_agents(self, test_claude_dir):
        """Test agent discovery."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)
        agents = discovery.discover_agents()

        assert len(agents) == 1
        assert "test-agent" in agents

        agent = agents["test-agent"]
        assert agent.name == "test-agent"
        assert agent.description == "Test agent for testing"
        assert agent.tools == ["Read", "Write"]
        assert agent.model == "sonnet"

    def test_discover_skills(self, test_claude_dir):
        """Test skill discovery."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)
        skills = discovery.discover_skills()

        assert len(skills) == 2
        assert "test-skill" in skills
        assert "wrapped-skill" in skills

        skill = skills["test-skill"]
        assert skill.name == "test-skill"
        assert skill.description == "Test skill for testing"
        assert skill.command == "test-skill"
        assert skill.user_interface is None

    def test_get_agent(self, test_claude_dir):
        """Test get_agent method."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        agent = discovery.get_agent("test-agent")
        assert agent is not None
        assert agent.name == "test-agent"

        missing = discovery.get_agent("missing-agent")
        assert missing is None

    def test_get_skill(self, test_claude_dir):
        """Test get_skill method."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        skill = discovery.get_skill("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"

        missing = discovery.get_skill("missing-skill")
        assert missing is None

    def test_validate_agents(self, test_claude_dir):
        """Test agent validation."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        validation = discovery.validate_agents(["test-agent", "missing-agent"])
        assert validation["test-agent"] is True
        assert validation["missing-agent"] is False

    def test_validate_skills(self, test_claude_dir):
        """Test skill validation."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        validation = discovery.validate_skills(["test-skill", "missing-skill"])
        assert validation["test-skill"] is True
        assert validation["missing-skill"] is False

    def test_build_agent_prompt_section(self, test_claude_dir):
        """Test agent prompt section generation."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        section = discovery.build_agent_prompt_section(["test-agent"])
        assert "test-agent" in section
        assert "Test agent for testing" in section
        assert "Task(subagent_type=" in section

    def test_build_skill_prompt_section(self, test_claude_dir):
        """Test skill prompt section generation."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        section = discovery.build_skill_prompt_section(["test-skill"])
        assert "test-skill" in section
        assert "Test skill for testing" in section
        assert "Skill(command=" in section

    def test_build_skill_prompt_excludes_wrapped(self, test_claude_dir):
        """Test that agent-wrapped skills are excluded from prompt."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        section = discovery.build_skill_prompt_section(["wrapped-skill"])
        assert "wrapped-skill" not in section

    def test_cache_works(self, test_claude_dir):
        """Test that caching works correctly."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        # First call - should scan directory
        agents1 = discovery.discover_agents()
        # Second call - should use cache
        agents2 = discovery.discover_agents()

        assert agents1 == agents2
        assert agents1 is agents2  # Same object reference

    def test_force_refresh(self, test_claude_dir):
        """Test force refresh bypasses cache."""
        discovery = AgentSkillDiscovery(claude_dir=test_claude_dir)

        # First call
        agents1 = discovery.discover_agents()

        # Add new agent
        (test_claude_dir / "agents" / "new-agent.md").write_text(
            """---
description: "New agent"
tools: []
model: "haiku"
---
"""
        )

        # Without refresh - should not see new agent
        agents2 = discovery.discover_agents()
        assert len(agents2) == 1

        # With refresh - should see new agent
        agents3 = discovery.discover_agents(force_refresh=True)
        assert len(agents3) == 2
