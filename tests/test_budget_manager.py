"""Tests for BudgetManager class."""

import os

import pytest
import pytest_asyncio

from src.budget_manager import BudgetManager


@pytest_asyncio.fixture
async def budget_manager(tmp_path):
    """Create a BudgetManager instance with temporary database."""
    db_path = tmp_path / "test_budgets.db"
    manager = BudgetManager(str(db_path))
    yield manager
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_check_budget_allows_within_limit(budget_manager):
    """Test that check_budget allows requests within budget limit."""
    # Set budget for project
    await budget_manager.set_budget("test-project", 10000, "Test Project")

    # Check should pass - well within budget
    result = await budget_manager.check_budget("test-project", 1000)
    assert result is True

    # Track some usage
    await budget_manager.track_usage("test-project", "haiku", 2000, 0.01)

    # Check should still pass - 2000 + 3000 = 5000 < 10000
    result = await budget_manager.check_budget("test-project", 3000)
    assert result is True


@pytest.mark.asyncio
async def test_check_budget_blocks_over_limit(budget_manager):
    """Test that check_budget blocks requests that would exceed limit."""
    # Set budget for project
    await budget_manager.set_budget("test-project", 5000, "Test Project")

    # Track usage close to limit
    await budget_manager.track_usage("test-project", "sonnet", 4500, 0.05)

    # Check should fail - 4500 + 1000 = 5500 > 5000
    result = await budget_manager.check_budget("test-project", 1000)
    assert result is False

    # Check should pass - 4500 + 500 = 5000 = 5000
    result = await budget_manager.check_budget("test-project", 500)
    assert result is True


@pytest.mark.asyncio
async def test_check_budget_no_limit(budget_manager):
    """Test that projects without budget limits are always allowed."""
    # No budget set - should allow
    result = await budget_manager.check_budget("unlimited-project", 999999)
    assert result is True

    # Set unlimited budget (None)
    await budget_manager.set_budget("unlimited-project", None, "Unlimited")

    # Should still allow
    result = await budget_manager.check_budget("unlimited-project", 999999)
    assert result is True


@pytest.mark.asyncio
async def test_track_usage(budget_manager):
    """Test that usage tracking correctly records data."""
    # Track multiple usage events
    await budget_manager.track_usage("project-1", "haiku", 1000, 0.005)
    await budget_manager.track_usage("project-1", "sonnet", 2000, 0.02)
    await budget_manager.track_usage("project-1", "haiku", 500, 0.0025)

    # Get usage stats
    stats = await budget_manager.get_usage("project-1", "month")

    # Verify totals
    assert stats["total_tokens"] == 3500
    assert abs(stats["total_cost"] - 0.0275) < 0.0001  # Float comparison

    # Verify by_model breakdown
    assert "haiku" in stats["by_model"]
    assert stats["by_model"]["haiku"]["tokens"] == 1500
    assert abs(stats["by_model"]["haiku"]["cost"] - 0.0075) < 0.0001

    assert "sonnet" in stats["by_model"]
    assert stats["by_model"]["sonnet"]["tokens"] == 2000
    assert abs(stats["by_model"]["sonnet"]["cost"] - 0.02) < 0.0001


@pytest.mark.asyncio
async def test_get_usage_stats(budget_manager):
    """Test usage statistics retrieval with different periods."""
    # Set budget
    await budget_manager.set_budget("stats-project", 10000, "Stats Project")

    # Track usage
    await budget_manager.track_usage("stats-project", "haiku", 1000, 0.01)
    await budget_manager.track_usage("stats-project", "sonnet", 2000, 0.02)
    await budget_manager.track_usage("stats-project", "opus", 1500, 0.03)

    # Get monthly stats
    stats = await budget_manager.get_usage("stats-project", "month")

    assert stats["total_tokens"] == 4500
    assert abs(stats["total_cost"] - 0.06) < 0.0001
    assert stats["limit"] == 10000
    assert stats["remaining"] == 5500

    # Verify all models are tracked
    assert len(stats["by_model"]) == 3
    assert "haiku" in stats["by_model"]
    assert "sonnet" in stats["by_model"]
    assert "opus" in stats["by_model"]


@pytest.mark.asyncio
async def test_get_usage_periods(budget_manager):
    """Test that different period parameters work correctly."""
    await budget_manager.track_usage("period-test", "haiku", 1000, 0.01)

    # Test different periods
    month_stats = await budget_manager.get_usage("period-test", "month")
    assert month_stats["total_tokens"] == 1000

    week_stats = await budget_manager.get_usage("period-test", "week")
    assert week_stats["total_tokens"] == 1000

    day_stats = await budget_manager.get_usage("period-test", "day")
    assert day_stats["total_tokens"] == 1000

    # Test invalid period
    with pytest.raises(ValueError):
        await budget_manager.get_usage("period-test", "invalid")


@pytest.mark.asyncio
async def test_set_budget(budget_manager):
    """Test setting and updating project budgets."""
    # Set initial budget
    await budget_manager.set_budget("budget-test", 5000, "Budget Test")

    # Verify budget was set
    stats = await budget_manager.get_usage("budget-test", "month")
    assert stats["limit"] == 5000

    # Update budget
    await budget_manager.set_budget("budget-test", 10000)

    # Verify update
    stats = await budget_manager.get_usage("budget-test", "month")
    assert stats["limit"] == 10000

    # Update name too
    await budget_manager.set_budget("budget-test", 15000, "Updated Name")

    # Verify both updated
    stats = await budget_manager.get_usage("budget-test", "month")
    assert stats["limit"] == 15000


@pytest.mark.asyncio
async def test_set_budget_unlimited(budget_manager):
    """Test setting unlimited budget."""
    # Set limited budget first
    await budget_manager.set_budget("unlimited-test", 5000, "Limited")

    # Change to unlimited
    await budget_manager.set_budget("unlimited-test", None)

    # Verify unlimited
    stats = await budget_manager.get_usage("unlimited-test", "month")
    assert stats["limit"] is None
    assert stats["remaining"] is None


@pytest.mark.asyncio
async def test_multiple_projects(budget_manager):
    """Test that multiple projects are tracked independently."""
    # Set up two projects
    await budget_manager.set_budget("project-a", 5000, "Project A")
    await budget_manager.set_budget("project-b", 8000, "Project B")

    # Track usage for both
    await budget_manager.track_usage("project-a", "haiku", 2000, 0.01)
    await budget_manager.track_usage("project-b", "sonnet", 3000, 0.02)

    # Verify independent tracking
    stats_a = await budget_manager.get_usage("project-a", "month")
    assert stats_a["total_tokens"] == 2000
    assert stats_a["limit"] == 5000
    assert stats_a["remaining"] == 3000

    stats_b = await budget_manager.get_usage("project-b", "month")
    assert stats_b["total_tokens"] == 3000
    assert stats_b["limit"] == 8000
    assert stats_b["remaining"] == 5000


@pytest.mark.asyncio
async def test_database_persistence(tmp_path):
    """Test that data persists across BudgetManager instances."""
    db_path = tmp_path / "persistence_test.db"

    # Create first instance and add data
    manager1 = BudgetManager(str(db_path))
    await manager1.set_budget("persist-test", 10000, "Persistence Test")
    await manager1.track_usage("persist-test", "haiku", 1000, 0.01)

    # Create second instance with same database
    manager2 = BudgetManager(str(db_path))
    stats = await manager2.get_usage("persist-test", "month")

    # Verify data persisted
    assert stats["total_tokens"] == 1000
    assert stats["limit"] == 10000
    assert stats["remaining"] == 9000

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_empty_project_usage(budget_manager):
    """Test getting usage for project with no tracked usage."""
    stats = await budget_manager.get_usage("empty-project", "month")

    assert stats["total_tokens"] == 0
    assert stats["total_cost"] == 0.0
    assert stats["by_model"] == {}
    assert stats["limit"] is None
    assert stats["remaining"] is None
