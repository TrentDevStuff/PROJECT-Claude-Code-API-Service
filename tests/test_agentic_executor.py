"""
Tests for agentic_executor.py

Comprehensive test coverage for AgenticExecutor including:
- Simple task execution
- Tool usage
- Agent spawning
- Skill invocation
- Timeout enforcement
- Cost limit enforcement
- Artifact collection
- Execution log capture
- Error handling
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agentic_executor import (
    AgenticExecutor,
    AgenticTaskRequest,
    ExecutionLogEntry,
)
from src.budget_manager import BudgetManager
from src.worker_pool import TaskResult, TaskStatus


def make_task_result(completion, input_tokens, output_tokens, cost):
    """Helper to create TaskResult with proper structure."""
    return TaskResult(
        task_id="test-123",
        status=TaskStatus.COMPLETED,
        completion=completion,
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        cost=cost,
        error=None,
    )


@pytest.fixture
def mock_worker_pool():
    """Mock WorkerPool for testing."""
    pool = Mock()
    pool.submit = Mock(return_value="test-task-123")
    return pool


@pytest.fixture
def mock_budget_manager():
    """Mock BudgetManager for testing."""
    manager = AsyncMock(spec=BudgetManager)
    manager.check_budget = AsyncMock(return_value=True)
    manager.track_usage = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def executor(mock_worker_pool, mock_budget_manager):
    """AgenticExecutor instance with mocked dependencies."""
    exec_instance = AgenticExecutor(
        worker_pool=mock_worker_pool, budget_manager=mock_budget_manager
    )
    # Stub out agent/skill discovery so tests don't fail on missing names
    exec_instance.agent_discovery.validate_agents = lambda names: dict.fromkeys(names, True)
    exec_instance.agent_discovery.validate_skills = lambda names: dict.fromkeys(names, True)
    return exec_instance


@pytest.mark.asyncio
async def test_simple_agentic_task(executor, mock_worker_pool, mock_budget_manager):
    """Test basic agentic task execution."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Task completed successfully", input_tokens=100, output_tokens=50, cost=0.01
        )
    )

    request = AgenticTaskRequest(
        description="Analyze src/worker_pool.py for issues",
        allow_tools=["Read"],
        timeout=60,
        max_cost=0.50,
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    assert "Task completed" in response.result["summary"]
    assert response.usage["total_cost"] == 0.01
    assert response.usage["input_tokens"] == 100
    assert response.usage["output_tokens"] == 50

    mock_budget_manager.check_budget.assert_called_once()
    mock_budget_manager.track_usage.assert_called_once()


@pytest.mark.asyncio
async def test_tool_usage(executor, mock_worker_pool, mock_budget_manager):
    """Test task with tool usage (Read, Grep, Bash)."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Used Read to analyze file, found 3 issues",
            input_tokens=200,
            output_tokens=100,
            cost=0.02,
        )
    )

    request = AgenticTaskRequest(
        description="Check file for race conditions",
        allow_tools=["Read", "Grep", "Bash"],
        timeout=120,
        max_cost=1.00,
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    prompt = mock_worker_pool.submit.call_args[1]["prompt"]
    assert "Read" in prompt or "Grep" in prompt or "Bash" in prompt


@pytest.mark.asyncio
async def test_agent_spawning(executor, mock_worker_pool, mock_budget_manager):
    """Test task that spawns agents."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Spawned security-auditor agent, found vulnerabilities",
            input_tokens=500,
            output_tokens=200,
            cost=0.05,
        )
    )

    request = AgenticTaskRequest(
        description="Security audit of API",
        allow_agents=["security-auditor"],
        timeout=300,
        max_cost=1.00,
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    # Model should be sonnet for agent-based tasks
    assert mock_worker_pool.submit.call_args[1]["model"] == "sonnet"


@pytest.mark.asyncio
async def test_skill_invocation(executor, mock_worker_pool, mock_budget_manager):
    """Test task that invokes skills."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Invoked vulnerability-scanner skill, report generated",
            input_tokens=300,
            output_tokens=150,
            cost=0.03,
        )
    )

    request = AgenticTaskRequest(
        description="Run vulnerability scan",
        allow_skills=["vulnerability-scanner"],
        timeout=180,
        max_cost=1.00,
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    prompt = mock_worker_pool.submit.call_args[1]["prompt"]
    assert "vulnerability-scanner" in prompt


@pytest.mark.asyncio
async def test_timeout_enforcement(executor, mock_worker_pool, mock_budget_manager):
    """Test that long tasks timeout correctly."""
    mock_worker_pool.get_result = Mock(side_effect=TimeoutError("Task timed out"))

    request = AgenticTaskRequest(description="Long-running analysis", timeout=10, max_cost=1.00)

    response = await executor.execute_task(request)

    assert response.status == "timeout"
    assert "timeout" in response.result["error"].lower()


@pytest.mark.asyncio
async def test_cost_limit_enforcement(executor, mock_worker_pool, mock_budget_manager):
    """Test that tasks halt at cost cap."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Expensive task output...",
            input_tokens=10000,
            output_tokens=5000,
            cost=2.50,  # Exceeds limit
        )
    )

    request = AgenticTaskRequest(
        description="Complex analysis", timeout=300, max_cost=1.00  # Lower than actual cost
    )

    response = await executor.execute_task(request)

    assert response.status == "cost_exceeded"
    assert "exceeded" in response.result["error"].lower()
    assert response.usage["total_cost"] == 2.50


@pytest.mark.asyncio
async def test_artifact_collection(executor, mock_worker_pool, mock_budget_manager):
    """Test that artifacts are collected from workspace."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Generated report.md and analysis.json",
            input_tokens=200,
            output_tokens=100,
            cost=0.02,
        )
    )

    # Create mock workspace with artifacts
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir)
        (workspace_dir / "report.md").write_text("# Analysis Report")
        (workspace_dir / "analysis.json").write_text('{"findings": []}')

        # Patch _create_workspace to return our test directory
        with patch.object(executor, "_create_workspace", return_value=workspace_dir):
            request = AgenticTaskRequest(
                description="Generate analysis report",
                allow_tools=["Write"],
                timeout=60,
                max_cost=0.50,
            )

            response = await executor.execute_task(request)

            assert response.status == "completed"
            assert len(response.artifacts) == 2
            assert any("report.md" in a.path for a in response.artifacts)
            assert any("analysis.json" in a.path for a in response.artifacts)


@pytest.mark.asyncio
async def test_execution_log(executor, mock_worker_pool, mock_budget_manager):
    """Test that execution log is captured."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Performed analysis using Read and Grep tools",
            input_tokens=150,
            output_tokens=75,
            cost=0.015,
        )
    )

    request = AgenticTaskRequest(
        description="Simple analysis", allow_tools=["Read", "Grep"], timeout=60, max_cost=0.50
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    assert len(response.execution_log) > 0
    assert all(isinstance(entry, ExecutionLogEntry) for entry in response.execution_log)


@pytest.mark.asyncio
async def test_error_handling(executor, mock_worker_pool, mock_budget_manager):
    """Test graceful error handling."""
    mock_worker_pool.get_result = Mock(side_effect=Exception("Unexpected error"))

    request = AgenticTaskRequest(description="Task that fails", timeout=60, max_cost=0.50)

    response = await executor.execute_task(request)

    assert response.status == "failed"
    assert "error" in response.result
    assert "Unexpected error" in response.result["error"]


@pytest.mark.asyncio
async def test_insufficient_budget(executor, mock_worker_pool, mock_budget_manager):
    """Test handling when budget is insufficient."""
    mock_budget_manager.check_budget = AsyncMock(return_value=False)

    request = AgenticTaskRequest(description="Expensive task", timeout=300, max_cost=5.00)

    response = await executor.execute_task(request)

    assert response.status == "failed"
    assert "budget" in response.result["error"].lower()


@pytest.mark.asyncio
async def test_model_auto_selection(executor, mock_worker_pool, mock_budget_manager):
    """Test that model is auto-selected when not specified."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Simple task completed", input_tokens=50, output_tokens=25, cost=0.005
        )
    )

    request = AgenticTaskRequest(description="Simple question", timeout=30, max_cost=0.10)

    response = await executor.execute_task(request)

    assert response.status == "completed"
    model_used = mock_worker_pool.submit.call_args[1]["model"]
    assert model_used in ["haiku", "sonnet", "opus"]


@pytest.mark.asyncio
async def test_model_explicit_selection(executor, mock_worker_pool, mock_budget_manager):
    """Test that explicitly specified model is used."""
    mock_worker_pool.get_result = Mock(
        return_value=make_task_result(
            completion="Task completed with opus", input_tokens=500, output_tokens=200, cost=0.15
        )
    )

    request = AgenticTaskRequest(
        description="Complex analysis", model="opus", timeout=300, max_cost=1.00
    )

    response = await executor.execute_task(request)

    assert response.status == "completed"
    assert mock_worker_pool.submit.call_args[1]["model"] == "opus"


@pytest.mark.asyncio
async def test_validation_timeout_limit(executor):
    """Test that timeout validation works."""
    with pytest.raises(ValueError, match="Timeout cannot exceed 600"):
        request = AgenticTaskRequest(description="Test task", timeout=700)
        await executor.execute_task(request)


@pytest.mark.asyncio
async def test_validation_cost_limit(executor):
    """Test that cost validation works."""
    with pytest.raises(ValueError, match="Max cost cannot exceed"):
        request = AgenticTaskRequest(description="Test task", max_cost=15.00)
        await executor.execute_task(request)


@pytest.mark.asyncio
async def test_validation_description_required(executor):
    """Test that description is required."""
    with pytest.raises(ValueError, match="Description is required"):
        request = AgenticTaskRequest(description="")
        await executor.execute_task(request)


@pytest.mark.asyncio
async def test_token_estimation(executor):
    """Test that token estimation is reasonable."""
    request_with_tools = AgenticTaskRequest(
        description="Analyze file", allow_tools=["Read", "Grep"]
    )
    estimate_tools = executor._estimate_tokens(request_with_tools, "sonnet")

    request_with_agents = AgenticTaskRequest(
        description="Security audit", allow_agents=["security-auditor"]
    )
    estimate_agents = executor._estimate_tokens(request_with_agents, "sonnet")

    assert estimate_agents > estimate_tools
    assert estimate_tools > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
