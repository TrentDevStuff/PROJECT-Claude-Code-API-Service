"""
Worker Pool Manager for Claude CLI processes.

Manages a pool of Claude CLI subprocess workers with:
- Process pooling with configurable max workers
- Task queue system for when workers are busy
- Timeout handling
- PID tracking and automatic cleanup
- Thread-safe operations
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Queue


class TaskStatus(Enum):
    """Status of a submitted task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass
class TaskResult:
    """Result of a completed task."""

    task_id: str
    status: TaskStatus
    completion: str | None = None
    usage: dict[str, int] | None = None
    cost: float | None = None
    error: str | None = None


@dataclass
class Task:
    """Internal task representation."""

    task_id: str
    prompt: str
    model: str
    project_id: str
    status: TaskStatus = TaskStatus.PENDING
    process: subprocess.Popen | None = None
    temp_dir: Path | None = None
    result: TaskResult | None = None
    start_time: float | None = None
    timeout: float = 30.0
    working_directory: str | None = None
    allowed_tools: list[str] | None = None
    done_event: threading.Event = None

    def __post_init__(self):
        if self.done_event is None:
            self.done_event = threading.Event()


class WorkerPool:
    """
    Manages a pool of Claude CLI worker processes.

    Features:
    - Configurable max concurrent workers
    - Task queue for overflow
    - Automatic worker cleanup
    - Timeout handling
    - PID tracking
    """

    # Cost per million tokens (as of Jan 2026)
    COST_PER_MTK = {
        "haiku": {"input": 0.25, "output": 1.25},
        "sonnet": {"input": 3.00, "output": 15.00},
        "opus": {"input": 15.00, "output": 75.00},
    }

    def __init__(self, max_workers: int = 5, mcp_config: str = ""):
        """
        Initialize the worker pool.

        Args:
            max_workers: Maximum number of concurrent Claude CLI processes
            mcp_config: Path to MCP server config JSON file (passed to claude --mcp-config)
        """
        self.max_workers = max_workers
        self.mcp_config = mcp_config
        self.tasks: dict[str, Task] = {}
        self.task_queue: Queue = Queue()
        self.active_workers = 0
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.running = False

    def start(self):
        """Start the worker pool monitor thread."""
        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """Stop the worker pool and cleanup all tasks."""
        self.drain(timeout=5)

    def drain(self, timeout: int = 30) -> tuple:
        """
        Gracefully drain the worker pool.

        Stops accepting new tasks, waits for active tasks to finish up to
        *timeout* seconds, then SIGTERMs stragglers (with a 5 s grace
        period before SIGKILL).

        Returns:
            (completed, killed) — counts of tasks that finished vs were force-killed.
        """
        import signal

        self.running = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=min(timeout, 5.0))

        completed = 0
        killed = 0

        # Wait for active tasks to finish
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                still_running = [
                    t for t in self.tasks.values() if t.process and t.process.poll() is None
                ]
            if not still_running:
                break
            time.sleep(0.5)

        # Count completed, SIGTERM remaining
        with self.lock:
            for task in self.tasks.values():
                if task.process is None:
                    continue
                if task.process.poll() is not None:
                    completed += 1
                else:
                    # Still running after timeout — send SIGTERM
                    try:
                        task.process.send_signal(signal.SIGTERM)
                    except OSError:
                        pass

        # Give SIGTERM 5 s to take effect, then SIGKILL
        term_deadline = time.time() + 5
        while time.time() < term_deadline:
            with self.lock:
                stragglers = [
                    t for t in self.tasks.values() if t.process and t.process.poll() is None
                ]
            if not stragglers:
                break
            time.sleep(0.5)

        with self.lock:
            for task in self.tasks.values():
                if task.process and task.process.poll() is None:
                    try:
                        task.process.kill()
                        task.process.wait(timeout=2.0)
                    except Exception:
                        pass
                    killed += 1
                self._cleanup_task(task)

        return completed, killed

    def submit(
        self,
        prompt: str,
        model: str = "sonnet",
        project_id: str = "default",
        timeout: float = 30.0,
        working_directory: str | None = None,
        allowed_tools: list[str] | None = None,
    ) -> str:
        """
        Submit a task to the worker pool.

        Args:
            prompt: The prompt to send to Claude
            model: Model to use (haiku, sonnet, opus)
            project_id: Project identifier for tracking
            timeout: Timeout in seconds (default 30s)
            working_directory: Optional working directory for claude -p (loads CLAUDE.md/rules)
            allowed_tools: Optional list of tools to enable via --allowedTools

        Returns:
            task_id: Unique identifier for this task
        """
        task_id = str(uuid.uuid4())

        task = Task(
            task_id=task_id,
            prompt=prompt,
            model=model,
            project_id=project_id,
            timeout=timeout,
            working_directory=working_directory,
            allowed_tools=allowed_tools,
        )

        with self.lock:
            self.tasks[task_id] = task
            # Start immediately if capacity exists, otherwise queue
            if self.active_workers < self.max_workers:
                self._start_task_locked(task_id)
            else:
                self.task_queue.put(task_id)

        # Ensure monitor is running
        if not self.running:
            self.start()

        return task_id

    def get_result(self, task_id: str, timeout: float = 30.0) -> TaskResult:
        """
        Get the result of a submitted task (blocking).

        Args:
            task_id: The task identifier returned by submit()
            timeout: How long to wait for completion (seconds)

        Returns:
            TaskResult with completion, usage, and cost information

        Raises:
            ValueError: If task_id not found
            TimeoutError: If task doesn't complete within timeout
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.tasks[task_id]

        # Wait for completion using event (no polling)
        if task.done_event.wait(timeout=timeout):
            return task.result

        # Timeout - kill the task and capture any partial output
        with self.lock:
            task = self.tasks[task_id]
            stderr_capture = ""
            stdout_capture = ""
            if task.process and task.process.poll() is None:
                # Try to capture partial output before killing
                try:
                    stdout_capture, stderr_capture = task.process.communicate(timeout=2.0)
                except Exception:
                    pass
                try:
                    task.process.kill()
                except Exception:
                    pass
                task.status = TaskStatus.TIMEOUT

            # Also check debug log if it exists
            debug_log = ""
            if task.temp_dir:
                debug_path = task.temp_dir / "stderr.log"
                if debug_path.exists():
                    debug_log = debug_path.read_text()[-2000:]  # last 2000 chars

            error_msg = f"Task timed out after {timeout} seconds"
            if stderr_capture:
                error_msg += f"\nStderr: {stderr_capture[:2000]}"
            if stdout_capture:
                error_msg += f"\nPartial stdout: {stdout_capture[:2000]}"
            if debug_log:
                error_msg += f"\nDebug log: {debug_log}"

            task.result = TaskResult(
                task_id=task_id,
                status=TaskStatus.TIMEOUT,
                error=error_msg,
            )
            task.done_event.set()

        return task.result

    def kill(self, task_id: str) -> bool:
        """
        Terminate a running task.

        Args:
            task_id: The task identifier to kill

        Returns:
            True if task was killed, False if not found or already finished
        """
        with self.lock:
            if task_id not in self.tasks:
                return False

            task = self.tasks[task_id]

            if task.process and task.process.poll() is None:
                task.process.kill()
                task.status = TaskStatus.KILLED
                task.result = TaskResult(
                    task_id=task_id, status=TaskStatus.KILLED, error="Task was killed by user"
                )
                task.done_event.set()
                self.active_workers -= 1
                self._cleanup_task(task)
                return True

        return False

    def get_active_pids(self) -> dict[str, int]:
        """
        Get PIDs of all active worker processes.

        Returns:
            Dict mapping task_id to PID
        """
        pids = {}
        with self.lock:
            for task_id, task in self.tasks.items():
                if task.process and task.process.poll() is None:
                    pids[task_id] = task.process.pid
        return pids

    def _monitor_loop(self):
        """Main monitoring loop - processes queue and checks worker status."""
        while self.running:
            # Process queue if we have capacity
            with self.lock:
                can_start = self.active_workers < self.max_workers

            if can_start:
                try:
                    task_id = self.task_queue.get(timeout=0.5)
                    self._start_task(task_id)
                except Empty:
                    pass

            # Check for completed tasks
            self._check_completed_tasks()

            time.sleep(0.01)

    def _start_task(self, task_id: str):
        """Start executing a task (acquires lock)."""
        with self.lock:
            self._start_task_locked(task_id)

    def _start_task_locked(self, task_id: str):
        """Start executing a task (caller must hold self.lock)."""
        task = self.tasks.get(task_id)
        if not task:
            return

        # Re-check capacity under lock to prevent races
        if self.active_workers >= self.max_workers:
            self.task_queue.put(task_id)
            return

        # Create temp directory for this task
        task.temp_dir = Path(tempfile.mkdtemp(prefix=f"claude_task_{task_id[:8]}_"))
        prompt_file = task.temp_dir / "prompt.txt"

        # Write prompt to file
        prompt_file.write_text(task.prompt)

        # Build command - use shell string for proper prompt handling
        # This matches the orchestrator's daemon pattern
        claude_path = shutil.which("claude") or "claude"
        cmd = (
            f'{claude_path} -p "$(cat {prompt_file})" '
            f"--model {task.model} "
            f"--output-format json"
        )

        # Append allowed tools if specified
        if task.allowed_tools:
            tools_str = ",".join(task.allowed_tools)
            cmd += f" --allowedTools '{tools_str}'"
            # Non-interactive subprocess can't prompt for permissions
            cmd += " --permission-mode bypassPermissions"

        # Append MCP config if configured
        if self.mcp_config:
            mcp_path = Path(self.mcp_config).resolve()
            if mcp_path.exists():
                cmd += f" --mcp-config {mcp_path}"

        # Build clean environment for subprocess
        # Remove CLAUDECODE=1 which blocks nested Claude CLI sessions
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        # Determine working directory for subprocess
        cwd = None
        if task.working_directory:
            wd = Path(task.working_directory)
            if wd.is_dir():
                cwd = str(wd)

        # Start process — redirect stderr to file for real-time debug tracing
        stderr_log = task.temp_dir / "stderr.log"
        try:
            stderr_fh = open(stderr_log, "w")
            task.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=stderr_fh,
                shell=True,
                text=True,
                executable="/bin/bash",  # Use bash for $(cat ...) substitution
                env=env,
                cwd=cwd,
            )
            task.status = TaskStatus.RUNNING
            task.start_time = time.time()
            self.active_workers += 1

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=f"Failed to start process: {str(e)}",
            )
            task.done_event.set()
            self._cleanup_task(task)

    def _check_completed_tasks(self):
        """Check for completed tasks and process their results."""
        with self.lock:
            completed_tasks = []

            for task_id, task in self.tasks.items():
                if task.status != TaskStatus.RUNNING:
                    continue

                # Check if process is done
                if task.process and task.process.poll() is not None:
                    completed_tasks.append(task_id)
                    continue

                # Check for timeout
                if task.start_time and (time.time() - task.start_time) > task.timeout:
                    if task.process:
                        task.process.kill()
                    task.status = TaskStatus.TIMEOUT
                    task.result = TaskResult(
                        task_id=task_id,
                        status=TaskStatus.TIMEOUT,
                        error=f"Task timed out after {task.timeout} seconds",
                    )
                    task.done_event.set()
                    self.active_workers -= 1
                    completed_tasks.append(task_id)

            # Process completed tasks outside the iteration
            for task_id in completed_tasks:
                self._process_completed_task(task_id)

    def _process_completed_task(self, task_id: str):
        """Process a completed task and extract results."""
        task = self.tasks[task_id]

        if not task.process:
            return

        # Skip if already has a result (e.g., from timeout)
        if task.result:
            return

        returncode = task.process.returncode

        # Try to get stdout (stderr goes to file)
        try:
            stdout = task.process.stdout.read() if task.process.stdout else ""
        except (ValueError, OSError):
            stdout = ""

        # Read stderr from log file
        stderr = ""
        if task.temp_dir:
            stderr_path = task.temp_dir / "stderr.log"
            if stderr_path.exists():
                try:
                    stderr = stderr_path.read_text()
                except OSError:
                    pass

        if returncode == 0:
            try:
                # Parse JSON output from Claude CLI
                output = json.loads(stdout)

                # Extract usage information
                usage = output.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)

                # Calculate cost
                cost = self._calculate_cost(task.model, input_tokens, output_tokens)

                task.status = TaskStatus.COMPLETED
                task.result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    completion=output.get(
                        "result", ""
                    ),  # Fixed: Claude CLI returns "result" not "content"
                    usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    cost=cost,
                )
                task.done_event.set()

            except json.JSONDecodeError as e:
                task.status = TaskStatus.FAILED
                task.result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=f"Failed to parse JSON output: {str(e)}\nOutput: {stdout}\nStderr: {stderr[-2000:]}",
                )
                task.done_event.set()

        else:
            task.status = TaskStatus.FAILED
            task.result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=f"Process exited with code {returncode}\nStderr: {stderr}",
            )
            task.done_event.set()

        self.active_workers -= 1
        self._cleanup_task(task)

    def _cleanup_task(self, task: Task):
        """Clean up temporary files for a task."""
        if task.temp_dir and task.temp_dir.exists():
            try:
                import shutil

                shutil.rmtree(task.temp_dir)
            except Exception:
                pass  # Best effort cleanup

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost of a task in USD.

        Args:
            model: Model name (haiku, sonnet, opus)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        if model not in self.COST_PER_MTK:
            return 0.0

        rates = self.COST_PER_MTK[model]
        input_cost = (input_tokens / 1_000_000) * rates["input"]
        output_cost = (output_tokens / 1_000_000) * rates["output"]

        return input_cost + output_cost
