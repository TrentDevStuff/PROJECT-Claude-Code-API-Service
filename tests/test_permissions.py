"""
Tests for Permission Manager.

Tests permission validation, profile management, and API key access control.
"""

import os

import pytest

from src.permission_manager import DEFAULT_PROFILES, PermissionManager


@pytest.fixture
def permission_manager():
    """Create test permission manager with temporary database"""
    db_path = "test_permissions.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    manager = PermissionManager(db_path=db_path)
    yield manager

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


def test_permission_validation_allowed(permission_manager):
    """Test successful permission validation"""
    # Create a test API key with permissions
    permission_manager.set_profile(
        "test-key-1",
        {
            "allowed_tools": ["Read", "Grep", "Bash"],
            "blocked_tools": [],
            "allowed_agents": ["security-auditor"],
            "allowed_skills": ["code-analyzer"],
            "max_concurrent_tasks": 5,
            "max_cpu_cores": 2.0,
            "max_memory_gb": 2.0,
            "max_execution_seconds": 600,
            "max_cost_per_task": 5.00,
            "network_access": True,
            "filesystem_access": "readonly",
            "workspace_size_mb": 200,
        },
    )

    # Validate request
    validation = permission_manager.validate_task_request(
        api_key="test-key-1",
        requested_tools=["Read", "Grep"],
        requested_agents=["security-auditor"],
        requested_skills=["code-analyzer"],
        timeout=300,
        max_cost=2.00,
    )

    assert validation.allowed is True
    assert "permission checks passed" in validation.reason.lower()
    assert validation.profile is not None


def test_tool_whitelist_enforcement(permission_manager):
    """Test that disallowed tools are blocked"""
    permission_manager.set_profile(
        "test-key-2",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": [],
            "allowed_agents": [],
            "allowed_skills": [],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    # Try to use a tool not in whitelist
    validation = permission_manager.validate_task_request(
        api_key="test-key-2", requested_tools=["Write"], timeout=60, max_cost=0.50
    )

    assert validation.allowed is False
    assert "not in allowed list" in validation.reason.lower()


def test_agent_whitelist_enforcement(permission_manager):
    """Test that disallowed agents are blocked"""
    permission_manager.set_profile(
        "test-key-3",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": [],
            "allowed_agents": ["security-auditor"],
            "allowed_skills": [],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    # Try to use an agent not in whitelist
    validation = permission_manager.validate_task_request(
        api_key="test-key-3",
        requested_tools=["Read"],
        requested_agents=["code-reviewer"],
        timeout=60,
        max_cost=0.50,
    )

    assert validation.allowed is False
    assert "agent" in validation.reason.lower()
    assert "not in allowed list" in validation.reason.lower()


def test_resource_limit_enforcement(permission_manager):
    """Test that resource limits are enforced"""
    permission_manager.set_profile(
        "test-key-4",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": [],
            "allowed_agents": [],
            "allowed_skills": [],
            "max_execution_seconds": 60,
            "max_cost_per_task": 0.50,
        },
    )

    # Try to exceed timeout limit
    validation = permission_manager.validate_task_request(
        api_key="test-key-4", requested_tools=["Read"], timeout=120, max_cost=0.25
    )

    assert validation.allowed is False
    assert "timeout" in validation.reason.lower()
    assert "exceeds limit" in validation.reason.lower()

    # Try to exceed cost limit
    validation = permission_manager.validate_task_request(
        api_key="test-key-4", requested_tools=["Read"], timeout=30, max_cost=1.00
    )

    assert validation.allowed is False
    assert "cost" in validation.reason.lower()
    assert "exceeds limit" in validation.reason.lower()


def test_permission_violation_logging(permission_manager):
    """Test that permission violations are properly detected"""
    permission_manager.set_profile(
        "test-key-5",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": ["Write", "Edit"],
            "allowed_agents": [],
            "allowed_skills": [],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    # Try to use a blocked tool
    validation = permission_manager.validate_task_request(
        api_key="test-key-5", requested_tools=["Write"], timeout=60, max_cost=0.50
    )

    assert validation.allowed is False
    assert "blocked" in validation.reason.lower()


def test_default_profiles(permission_manager):
    """Test that default profiles are correctly applied"""
    # Test free profile
    permission_manager.apply_default_profile("free-key", "free")
    profile = permission_manager.get_profile("free-key")

    assert profile is not None
    assert profile.allowed_tools == DEFAULT_PROFILES["free"]["allowed_tools"]
    assert profile.max_execution_seconds == DEFAULT_PROFILES["free"]["max_execution_seconds"]
    assert profile.max_cost_per_task == DEFAULT_PROFILES["free"]["max_cost_per_task"]

    # Test pro profile
    permission_manager.apply_default_profile("pro-key", "pro")
    profile = permission_manager.get_profile("pro-key")

    assert profile is not None
    assert profile.allowed_tools == DEFAULT_PROFILES["pro"]["allowed_tools"]
    assert profile.max_concurrent_tasks == DEFAULT_PROFILES["pro"]["max_concurrent_tasks"]

    # Test enterprise profile
    permission_manager.apply_default_profile("enterprise-key", "enterprise")
    profile = permission_manager.get_profile("enterprise-key")

    assert profile is not None
    assert "*" in profile.allowed_tools
    assert "*" in profile.allowed_agents
    assert profile.max_concurrent_tasks == DEFAULT_PROFILES["enterprise"]["max_concurrent_tasks"]


def test_blocked_tools(permission_manager):
    """Test that explicitly blocked tools are denied even if in allowed list"""
    permission_manager.set_profile(
        "test-key-6",
        {
            "allowed_tools": ["*"],  # All tools allowed
            "blocked_tools": ["Write", "Edit"],  # But these are blocked
            "allowed_agents": [],
            "allowed_skills": [],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    # Read should work (wildcard allowed, not blocked)
    validation = permission_manager.validate_task_request(
        api_key="test-key-6", requested_tools=["Read"], timeout=60, max_cost=0.50
    )

    assert validation.allowed is True

    # Write should fail (explicitly blocked)
    validation = permission_manager.validate_task_request(
        api_key="test-key-6", requested_tools=["Write"], timeout=60, max_cost=0.50
    )

    assert validation.allowed is False
    assert "blocked" in validation.reason.lower()


def test_no_profile_found(permission_manager):
    """Test behavior when no permission profile exists"""
    validation = permission_manager.validate_task_request(
        api_key="nonexistent-key", requested_tools=["Read"], timeout=60, max_cost=0.50
    )

    assert validation.allowed is False
    assert "no permission profile" in validation.reason.lower()


def test_profile_crud_operations(permission_manager):
    """Test create, read, update, delete operations on profiles"""
    # Create
    permission_manager.set_profile(
        "crud-key",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": [],
            "allowed_agents": [],
            "allowed_skills": [],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    profile = permission_manager.get_profile("crud-key")
    assert profile is not None
    assert profile.allowed_tools == ["Read"]

    # Update
    permission_manager.set_profile(
        "crud-key",
        {
            "allowed_tools": ["Read", "Grep"],
            "blocked_tools": [],
            "allowed_agents": ["security-auditor"],
            "allowed_skills": [],
            "max_execution_seconds": 600,
            "max_cost_per_task": 2.00,
        },
    )

    profile = permission_manager.get_profile("crud-key")
    assert profile is not None
    assert "Grep" in profile.allowed_tools
    assert "security-auditor" in profile.allowed_agents
    assert profile.max_execution_seconds == 600

    # Delete
    permission_manager.delete_profile("crud-key")
    profile = permission_manager.get_profile("crud-key")
    assert profile is None


def test_skill_whitelist_enforcement(permission_manager):
    """Test that disallowed skills are blocked"""
    permission_manager.set_profile(
        "test-key-7",
        {
            "allowed_tools": ["Read"],
            "blocked_tools": [],
            "allowed_agents": [],
            "allowed_skills": ["vulnerability-scanner"],
            "max_execution_seconds": 300,
            "max_cost_per_task": 1.00,
        },
    )

    # Try to use a skill not in whitelist
    validation = permission_manager.validate_task_request(
        api_key="test-key-7",
        requested_tools=["Read"],
        requested_skills=["code-analyzer"],
        timeout=60,
        max_cost=0.50,
    )

    assert validation.allowed is False
    assert "skill" in validation.reason.lower()
    assert "not in allowed list" in validation.reason.lower()


def test_wildcard_permissions(permission_manager):
    """Test wildcard permissions work correctly"""
    permission_manager.set_profile(
        "wildcard-key",
        {
            "allowed_tools": ["*"],
            "blocked_tools": [],
            "allowed_agents": ["*"],
            "allowed_skills": ["*"],
            "max_execution_seconds": 600,
            "max_cost_per_task": 10.00,
        },
    )

    # Any tool should work
    validation = permission_manager.validate_task_request(
        api_key="wildcard-key",
        requested_tools=["Read", "Write", "Edit", "Bash"],
        requested_agents=["security-auditor", "code-reviewer"],
        requested_skills=["any-skill"],
        timeout=300,
        max_cost=5.00,
    )

    assert validation.allowed is True
