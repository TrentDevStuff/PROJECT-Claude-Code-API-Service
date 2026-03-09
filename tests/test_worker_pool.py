"""
Tests for WorkerPool class.

Tests cover:
- Task submission and result retrieval
- Timeout handling
- Worker cleanup
- Concurrent workers
- PID tracking
- Queue system
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.worker_pool import TaskStatus, WorkerPool


@pytest.fixture
def worker_pool():
    """Create a WorkerPool instance for testing."""
    pool = WorkerPool(max_workers=3)
    yield pool
    pool.stop()


def test_worker_pool_initialization():
    """Test that WorkerPool initializes correctly."""
    pool = WorkerPool(max_workers=5)

    assert pool.max_workers == 5
    assert pool.active_workers == 0
    assert pool.tasks == {}
    assert not pool.running

    pool.stop()


def test_submit_task(worker_pool):
    """Test basic task submission."""
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    assert task_id is not None
    assert task_id in worker_pool.tasks

    task = worker_pool.tasks[task_id]
    assert task.prompt == "Test prompt"
    assert task.model == "haiku"
    assert task.project_id == "test-project"
    # Task starts immediately when workers are available (direct start optimization)
    assert task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)


def test_submit_multiple_tasks(worker_pool):
    """Test submitting multiple tasks."""
    task_ids = []

    for i in range(5):
        task_id = worker_pool.submit(
            prompt=f"Test prompt {i}", model="haiku", project_id="test-project"
        )
        task_ids.append(task_id)

    assert len(task_ids) == 5
    assert len(worker_pool.tasks) == 5
    assert all(tid in worker_pool.tasks for tid in task_ids)


@patch("src.worker_pool.subprocess.Popen")
def test_task_execution_success(mock_popen, worker_pool):
    """Test successful task execution."""
    # Mock the subprocess
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # Process completed
    mock_process.returncode = 0
    mock_process.pid = 12345
    json_output = json.dumps(
        {"result": "Test response", "usage": {"input_tokens": 100, "output_tokens": 50}}
    )
    mock_process.stdout.read.return_value = json_output
    mock_process.communicate.return_value = (json_output, "")
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    # Wait for processing
    time.sleep(1.0)

    result = worker_pool.get_result(task_id, timeout=5.0)

    assert result.status == TaskStatus.COMPLETED
    assert result.completion == "Test response"
    assert result.usage["input_tokens"] == 100
    assert result.usage["output_tokens"] == 50
    assert result.cost > 0


def test_get_result_nonexistent_task(worker_pool):
    """Test getting result for non-existent task."""
    with pytest.raises(ValueError, match="Task .* not found"):
        worker_pool.get_result("nonexistent-task-id")


@patch("src.worker_pool.subprocess.Popen")
def test_timeout_handling(mock_popen, worker_pool):
    """Test that tasks timeout correctly."""
    # Mock a process that never completes
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Process still running
    mock_process.pid = 12345
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(
        prompt="Test prompt", model="haiku", project_id="test-project", timeout=0.5  # 500ms timeout
    )

    # Wait for timeout
    result = worker_pool.get_result(task_id, timeout=2.0)

    assert result.status == TaskStatus.TIMEOUT
    assert "timed out" in result.error.lower()
    mock_process.kill.assert_called()


@patch("src.worker_pool.subprocess.Popen")
def test_kill_task(mock_popen, worker_pool):
    """Test killing a running task."""
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Process running
    mock_process.pid = 12345
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    # Give it time to start
    time.sleep(0.5)

    # Kill the task
    killed = worker_pool.kill(task_id)

    assert killed is True
    mock_process.kill.assert_called()

    task = worker_pool.tasks[task_id]
    assert task.status == TaskStatus.KILLED


def test_kill_nonexistent_task(worker_pool):
    """Test killing a non-existent task."""
    killed = worker_pool.kill("nonexistent-task-id")
    assert killed is False


@patch("src.worker_pool.subprocess.Popen")
def test_concurrent_workers(mock_popen, worker_pool):
    """Test that multiple workers can run concurrently."""
    # Create multiple mock processes
    mock_processes = []
    for i in range(3):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 10000 + i
        mock_processes.append(mock_process)

    mock_popen.side_effect = mock_processes

    worker_pool.start()

    # Submit 3 tasks (equal to max_workers)
    task_ids = []
    for i in range(3):
        task_id = worker_pool.submit(
            prompt=f"Test prompt {i}", model="haiku", project_id="test-project"
        )
        task_ids.append(task_id)

    # Give time for tasks to start
    time.sleep(1.0)

    # All 3 should be running
    assert worker_pool.active_workers == 3


@patch("src.worker_pool.subprocess.Popen")
def test_queue_system(mock_popen, worker_pool):
    """Test that tasks queue when workers are busy."""

    # Mock processes that never complete
    def create_mock_process():
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        return mock_process

    mock_popen.side_effect = [create_mock_process() for _ in range(5)]

    worker_pool.start()

    # Submit 5 tasks (more than max_workers=3)
    task_ids = []
    for i in range(5):
        task_id = worker_pool.submit(
            prompt=f"Test prompt {i}", model="haiku", project_id="test-project"
        )
        task_ids.append(task_id)

    # Give time for processing
    time.sleep(1.0)

    # Only 3 should be running (max_workers limit)
    assert worker_pool.active_workers == 3

    # Other tasks should be queued
    pending_count = sum(
        1 for task in worker_pool.tasks.values() if task.status == TaskStatus.PENDING
    )
    assert pending_count == 2


@patch("src.worker_pool.subprocess.Popen")
def test_get_active_pids(mock_popen, worker_pool):
    """Test PID tracking."""
    mock_processes = []
    expected_pids = {}

    for i in range(3):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 20000 + i
        mock_processes.append(mock_process)

    mock_popen.side_effect = mock_processes

    worker_pool.start()

    # Submit 3 tasks
    task_ids = []
    for i in range(3):
        task_id = worker_pool.submit(
            prompt=f"Test prompt {i}", model="haiku", project_id="test-project"
        )
        task_ids.append(task_id)
        expected_pids[task_id] = 20000 + i

    # Give time for tasks to start
    time.sleep(1.0)

    pids = worker_pool.get_active_pids()

    assert len(pids) == 3
    for task_id, pid in pids.items():
        assert pid == expected_pids[task_id]


@patch("src.worker_pool.subprocess.Popen")
def test_worker_cleanup(mock_popen, worker_pool):
    """Test that workers are cleaned up after completion."""
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # Completed
    mock_process.returncode = 0
    mock_process.pid = 12345
    json_output = json.dumps({"result": "Response", "usage": {"input_tokens": 10, "output_tokens": 5}})
    mock_process.stdout.read.return_value = json_output
    mock_process.communicate.return_value = (json_output, "")
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    # Wait for completion
    time.sleep(1.0)

    # Worker should be cleaned up
    assert worker_pool.active_workers == 0


def test_cost_calculation():
    """Test cost calculation for different models."""
    pool = WorkerPool()

    # Test Haiku (cheapest)
    haiku_cost = pool._calculate_cost("haiku", 1_000_000, 1_000_000)
    assert haiku_cost == pytest.approx(1.50)  # 0.25 + 1.25

    # Test Sonnet (medium)
    sonnet_cost = pool._calculate_cost("sonnet", 1_000_000, 1_000_000)
    assert sonnet_cost == pytest.approx(18.00)  # 3.00 + 15.00

    # Test Opus (most expensive)
    opus_cost = pool._calculate_cost("opus", 1_000_000, 1_000_000)
    assert opus_cost == pytest.approx(90.00)  # 15.00 + 75.00

    # Test unknown model
    unknown_cost = pool._calculate_cost("unknown", 1_000_000, 1_000_000)
    assert unknown_cost == 0.0

    pool.stop()


@patch("src.worker_pool.subprocess.Popen")
def test_process_failure_handling(mock_popen, worker_pool):
    """Test handling of process failures."""
    mock_process = MagicMock()
    mock_process.poll.return_value = 1  # Failed
    mock_process.returncode = 1
    mock_process.pid = 12345
    mock_process.stdout.read.return_value = ""
    mock_process.communicate.return_value = ("", "Error message")
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    # Wait for processing
    time.sleep(1.0)

    result = worker_pool.get_result(task_id, timeout=5.0)

    assert result.status == TaskStatus.FAILED
    assert "exited with code 1" in result.error


@patch("src.worker_pool.subprocess.Popen")
def test_invalid_json_output(mock_popen, worker_pool):
    """Test handling of invalid JSON output from Claude."""
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.returncode = 0
    mock_process.pid = 12345
    mock_process.stdout.read.return_value = "Invalid JSON {{{"
    mock_process.communicate.return_value = ("Invalid JSON {{{", "")
    mock_popen.return_value = mock_process

    worker_pool.start()
    task_id = worker_pool.submit(prompt="Test prompt", model="haiku", project_id="test-project")

    # Wait for processing
    time.sleep(1.0)

    result = worker_pool.get_result(task_id, timeout=5.0)

    assert result.status == TaskStatus.FAILED
    assert "Failed to parse JSON" in result.error


def test_custom_timeout(worker_pool):
    """Test custom timeout values."""
    task_id = worker_pool.submit(
        prompt="Test prompt",
        model="haiku",
        project_id="test-project",
        timeout=60.0,  # 60 second timeout
    )

    task = worker_pool.tasks[task_id]
    assert task.timeout == 60.0


import json  # Add this import for the tests

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
