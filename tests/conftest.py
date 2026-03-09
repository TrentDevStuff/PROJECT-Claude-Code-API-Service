"""
Shared test fixtures for integration tests.

Sets up test databases, API keys, and permission profiles.
"""

import shutil
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.agentic_executor import AgenticTaskResponse, ExecutionLogEntry
from src.auth import AuthManager
from src.permission_manager import PermissionManager


@pytest.fixture(scope="function")
def test_data_dir():
    """Create temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def test_auth_manager(test_data_dir):
    """Create AuthManager with test database."""
    db_path = f"{test_data_dir}/auth.db"
    auth_manager = AuthManager(db_path=db_path)

    # Create test API keys
    auth_manager.generate_key("test-project", rate_limit=100)  # Returns cc_... key

    # Create specific test keys
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(db_path)

    # test-key: enterprise permissions
    conn.execute(
        """
        INSERT INTO api_keys (key, project_id, rate_limit, created_at, revoked)
        VALUES (?, ?, ?, ?, 0)
        """,
        ("test-key", "test-project", 100, datetime.now()),
    )

    # limited-key: restricted permissions
    conn.execute(
        """
        INSERT INTO api_keys (key, project_id, rate_limit, created_at, revoked)
        VALUES (?, ?, ?, ?, 0)
        """,
        ("limited-key", "limited-project", 100, datetime.now()),
    )

    conn.commit()
    conn.close()

    return auth_manager


@pytest.fixture(scope="function")
def test_permission_manager(test_data_dir):
    """Create PermissionManager with test database."""
    db_path = f"{test_data_dir}/budgets.db"
    permission_manager = PermissionManager(db_path=db_path)

    # Create enterprise profile for test-key (allows all tools)
    permission_manager.apply_default_profile("test-key", "enterprise")

    # Create restricted profile for limited-key (permission tests)
    permission_manager.set_profile(
        "limited-key",
        {
            "allowed_tools": ["Read", "Grep"],
            "blocked_tools": ["Write", "Edit", "Bash"],
            "allowed_agents": [],
            "allowed_skills": [],
            "max_concurrent_tasks": 1,
            "max_cpu_cores": 0.5,
            "max_memory_gb": 0.5,
            "max_execution_seconds": 60,
            "max_cost_per_task": 0.10,
            "network_access": False,
            "filesystem_access": "readonly",
            "workspace_size_mb": 50,
        },
    )

    return permission_manager


@pytest.fixture(scope="function")
def test_app(test_auth_manager, test_permission_manager):
    """Create test FastAPI app with test services."""
    from main import app
    from src.api import initialize_services
    from src.audit_logger import AuditLogger
    from src.auth import initialize_auth
    from src.budget_manager import BudgetManager
    from src.websocket import initialize_websocket
    from src.worker_pool import WorkerPool

    # Create test worker pool and budget manager
    worker_pool = WorkerPool(max_workers=2)
    worker_pool.start()

    budget_manager = BudgetManager(db_path=test_permission_manager.db_path)
    audit_logger = AuditLogger(db_path=test_permission_manager.db_path)

    # Initialize services with test instances
    initialize_services(worker_pool, budget_manager, test_permission_manager)
    initialize_auth(test_auth_manager)
    initialize_websocket(worker_pool, budget_manager, test_permission_manager, audit_logger)

    yield app

    # Cleanup
    worker_pool.stop()


@pytest.fixture(scope="function")
def client(test_app):
    """Create test client with initialized app."""
    return TestClient(test_app)


@pytest.fixture
def mock_executor():
    """Mock AgenticExecutor for testing without actual execution."""
    with (
        patch("src.api.AgenticExecutor") as mock_api,
        patch("src.websocket.AgenticExecutor") as mock_ws,
    ):
        executor = Mock()
        executor.execute_task = AsyncMock(
            return_value=AgenticTaskResponse(
                task_id="test-task-123",
                status="completed",
                result={"summary": "Test task completed successfully"},
                execution_log=[
                    ExecutionLogEntry(
                        step=1,
                        timestamp="2026-01-30T20:00:00Z",
                        action="tool_call",
                        details={"tool": "Read", "file": "test.py"},
                    )
                ],
                artifacts=[],
                usage={
                    "model_used": "sonnet",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "total_cost": 0.00045,
                },
            )
        )
        mock_api.return_value = executor
        mock_ws.return_value = executor
        yield executor
