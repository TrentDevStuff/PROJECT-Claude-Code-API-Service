"""Tests for audit logging functionality."""

import json
import os
import tempfile

import pytest

from src.agentic_executor import AgenticExecutor, AgenticTaskRequest
from src.audit_logger import AuditLogger


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def audit_logger(temp_db):
    """Create an AuditLogger instance with temp database."""
    logger = AuditLogger(db_path=temp_db)
    return logger


@pytest.fixture
def executor(audit_logger):
    """Create an AgenticExecutor instance."""
    return AgenticExecutor(audit_logger=audit_logger)


@pytest.mark.asyncio
async def test_tool_call_logging(audit_logger):
    """Test logging of tool calls."""
    task_id = "task_001"
    api_key = "test_key_001"

    await audit_logger.log_tool_call(
        task_id=task_id, api_key=api_key, tool="Read", args={"file": "src/example.py"}
    )

    # Query and verify
    logs = await audit_logger.query_logs(filters={"task_id": task_id})
    assert len(logs) == 1
    assert logs[0]["event_type"] == "tool_call"
    assert logs[0]["severity"] == "info"
    details = json.loads(logs[0]["details"])
    assert details["tool"] == "Read"
    assert details["args"]["file"] == "src/example.py"


@pytest.mark.asyncio
async def test_security_event_logging(audit_logger, caplog):
    """Test logging of security events with alerts."""
    import logging

    task_id = "task_002"
    api_key = "test_key_002"

    with caplog.at_level(logging.CRITICAL, logger="src.audit_logger"):
        await audit_logger.log_security_event(
            task_id=task_id,
            api_key=api_key,
            event="blocked_command",
            details={"command": "rm -rf /", "reason": "dangerous"},
        )

    # Verify alert was logged at CRITICAL level
    assert any(
        "SECURITY ALERT" in r.message and "blocked_command" in r.message for r in caplog.records
    )

    # Query and verify in database
    logs = await audit_logger.query_logs(filters={"task_id": task_id})
    assert len(logs) == 1
    assert logs[0]["event_type"] == "security_event"
    assert logs[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_log_query(audit_logger):
    """Test querying audit logs with filters."""
    # Create multiple log entries
    for i in range(5):
        await audit_logger.log_tool_call(
            task_id="task_A", api_key="key_1", tool="Read", args={"file": f"file_{i}.py"}
        )

    for i in range(3):
        await audit_logger.log_bash_command(
            task_id="task_B", api_key="key_2", command=f"pytest test_{i}.py"
        )

    # Test filtering by task_id
    logs_a = await audit_logger.query_logs(filters={"task_id": "task_A"})
    assert len(logs_a) == 5

    # Test filtering by api_key
    logs_key2 = await audit_logger.query_logs(filters={"api_key": "key_2"})
    assert len(logs_key2) == 3

    # Test filtering by event_type
    tool_calls = await audit_logger.query_logs(filters={"event_type": "tool_call"})
    assert len(tool_calls) == 5

    bash_commands = await audit_logger.query_logs(filters={"event_type": "bash_command"})
    assert len(bash_commands) == 3


@pytest.mark.asyncio
async def test_analytics_queries(audit_logger):
    """Test analytics query methods."""
    # Log various events
    await audit_logger.log_tool_call("task_1", "key_1", "Read", {})
    await audit_logger.log_tool_call("task_1", "key_1", "Read", {})
    await audit_logger.log_tool_call("task_2", "key_1", "Write", {})
    await audit_logger.log_tool_call("task_3", "key_2", "Read", {})

    # Log security events
    await audit_logger.log_security_event("task_4", "key_1", "unauthorized_access", {})
    await audit_logger.log_security_event("task_5", "key_3", "permission_violation", {})

    # Test get_most_used_tools
    tools = await audit_logger.get_most_used_tools(days=7)
    assert "Read" in tools
    assert tools["Read"] >= 3

    # Test get_security_events_by_key
    security = await audit_logger.get_security_events_by_key(days=7)
    assert "key_1" in security
    assert security["key_1"] >= 1

    # Test get_avg_task_duration (should be very small for synchronous test)
    avg_duration = await audit_logger.get_avg_task_duration(days=7)
    assert avg_duration >= 0.0


@pytest.mark.asyncio
async def test_executor_task_execution(audit_logger):
    """Test agentic executor with audit logging."""
    from unittest.mock import AsyncMock, Mock

    from src.budget_manager import BudgetManager
    from src.worker_pool import TaskResult, TaskStatus

    # Create mocks
    mock_worker_pool = Mock()
    mock_worker_pool.submit = Mock(return_value="test-task-123")
    mock_worker_pool.get_result = Mock(
        return_value=TaskResult(
            task_id="test-123",
            status=TaskStatus.COMPLETED,
            completion="Task completed successfully",
            usage={"input_tokens": 100, "output_tokens": 50},
            cost=0.01,
            error=None,
        )
    )

    mock_budget_manager = AsyncMock(spec=BudgetManager)
    mock_budget_manager.check_budget = AsyncMock(return_value=True)
    mock_budget_manager.track_usage = AsyncMock(return_value=None)

    # Create executor with mocks and real audit logger
    executor = AgenticExecutor(
        worker_pool=mock_worker_pool, budget_manager=mock_budget_manager, audit_logger=audit_logger
    )

    request = AgenticTaskRequest(
        description="Test task execution with audit logging", api_key="test_exec_key", timeout=30
    )

    response = await executor.execute_task(request)

    # Response task_id is auto-generated UUID
    assert response.task_id is not None
    assert response.status == "completed"
    assert len(response.execution_log) > 0

    # Verify logs were created for this task
    logs = await audit_logger.query_logs(filters={"task_id": response.task_id})
    assert len(logs) > 0

    # Verify audit logger captured task lifecycle events
    event_types = {log["event_type"] for log in logs}
    assert "tool_call" in event_types  # task_start and task_completed are logged as tool_calls


def test_audit_logging_sync():
    """Test that audit logging module can be imported and instantiated."""
    logger = AuditLogger(db_path=":memory:")
    assert logger is not None
    assert logger.db_path == ":memory:"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
