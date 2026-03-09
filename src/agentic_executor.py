"""
Agentic Task Executor for Claude Code API.

Enables full Claude Code capabilities: tools, agents, skills, multi-turn reasoning.
Includes comprehensive audit logging integration.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .agent_discovery import AgentSkillDiscovery
from .audit_logger import AuditLogger
from .budget_manager import BudgetManager
from .model_router import auto_select_model
from .worker_pool import TaskResult, WorkerPool

# Pydantic Models


class AgenticTaskRequest(BaseModel):
    """Request model for agentic task execution."""

    description: str = Field(..., description="Natural language task description")
    allow_tools: list[str] = Field(
        default_factory=list, description="Allowed tools (Read, Grep, Bash, etc.)"
    )
    allow_agents: list[str] = Field(default_factory=list, description="Allowed agents to spawn")
    allow_skills: list[str] = Field(default_factory=list, description="Allowed skills to invoke")
    working_directory: str = Field(default="/project", description="Working directory for task")
    timeout: int = Field(default=300, description="Timeout in seconds (max 600)")
    max_cost: float = Field(default=1.00, description="Maximum cost in USD")
    model: str | None = Field(
        default=None, description="Model to use (haiku/sonnet/opus), auto-selected if None"
    )
    project_id: str = Field(default="default", description="Project ID for budget tracking")
    api_key: str = Field(default="default", description="API key for audit logging")


class ExecutionLogEntry(BaseModel):
    """Single entry in execution log."""

    step: int
    timestamp: str
    action: str  # "tool_call", "agent_spawn", "skill_invoke", "thinking", "result"
    details: dict[str, Any]


class Artifact(BaseModel):
    """Generated artifact from task execution."""

    type: str  # "file", "report", "data"
    path: str
    size_bytes: int
    created_at: str


class AgenticTaskResponse(BaseModel):
    """Response model for agentic task execution."""

    task_id: str
    status: str  # "completed", "failed", "timeout", "cost_exceeded"
    result: dict[str, Any]
    execution_log: list[ExecutionLogEntry]
    artifacts: list[Artifact]
    usage: dict[str, Any]


# Main Executor


class AgenticExecutor:
    """
    Core agentic task execution engine.

    Features:
    - Tool/agent/skill orchestration
    - Execution log capture
    - Artifact collection
    - Timeout enforcement
    - Cost limit enforcement
    - Budget integration
    - Comprehensive audit logging
    """

    def __init__(
        self,
        worker_pool: WorkerPool | None = None,
        budget_manager: BudgetManager | None = None,
        audit_logger: AuditLogger | None = None,
        agent_discovery: AgentSkillDiscovery | None = None,
    ):
        """
        Initialize AgenticExecutor.

        Args:
            worker_pool: WorkerPool instance (creates new if None)
            budget_manager: BudgetManager instance (creates new if None)
            audit_logger: AuditLogger instance for comprehensive event logging (creates new if None)
            agent_discovery: AgentSkillDiscovery instance for discovering available agents/skills
        """
        self.worker_pool = worker_pool or WorkerPool(max_workers=5)
        self.budget_manager = budget_manager or BudgetManager()
        self.audit_logger = audit_logger or AuditLogger()
        self.agent_discovery = agent_discovery or AgentSkillDiscovery()

    async def execute_task(self, request: AgenticTaskRequest) -> AgenticTaskResponse:
        """
        Execute an agentic task with full Claude Code capabilities.

        Args:
            request: AgenticTaskRequest with task configuration

        Returns:
            AgenticTaskResponse with results, logs, artifacts, usage

        Raises:
            ValueError: Invalid request parameters
            BudgetError: Insufficient budget
            TimeoutError: Task exceeded timeout
            CostExceededError: Task exceeded cost limit
        """
        task_id = str(uuid.uuid4())
        start_time = time.time()

        # Step 1: Validate request (before try block so validation errors raise)
        self._validate_request(request)

        # Log task start
        await self.audit_logger.log_tool_call(
            task_id,
            request.api_key,
            "task_start",
            {
                "description": request.description[:100],
                "allow_tools": request.allow_tools,
                "allow_agents": request.allow_agents,
                "allow_skills": request.allow_skills,
            },
        )

        try:
            # Step 2: Select model if not specified
            model = request.model or self._auto_select_model(request)

            # Step 3: Estimate tokens and check budget
            estimated_tokens = self._estimate_tokens(request, model)
            has_budget = await self.budget_manager.check_budget(
                project_id=request.project_id, estimated_tokens=estimated_tokens
            )

            if not has_budget:
                await self.audit_logger.log_security_event(
                    task_id,
                    request.api_key,
                    "budget_exceeded",
                    {"estimated_tokens": estimated_tokens},
                )
                return AgenticTaskResponse(
                    task_id=task_id,
                    status="failed",
                    result={"error": "Insufficient budget"},
                    execution_log=[],
                    artifacts=[],
                    usage={"estimated_tokens": estimated_tokens},
                )

            # Step 4: Build agentic prompt with configuration
            agentic_prompt = self._build_agentic_prompt(request)

            # Step 5: Create workspace for artifacts
            workspace_dir = self._create_workspace(task_id)

            # Step 6: Submit to worker pool
            worker_task_id = self.worker_pool.submit(
                prompt=agentic_prompt,
                model=model,
                project_id=request.project_id,
                timeout=request.timeout,
            )

            # Step 7: Get result (run in executor to avoid blocking event loop)
            loop = asyncio.get_event_loop()
            task_result: TaskResult = await loop.run_in_executor(
                None, self.worker_pool.get_result, worker_task_id, request.timeout + 10
            )

        except TimeoutError:
            await self.audit_logger.log_security_event(
                task_id, request.api_key, "timeout", {"timeout_seconds": request.timeout}
            )
            return AgenticTaskResponse(
                task_id=task_id,
                status="timeout",
                result={"error": f"Task exceeded timeout of {request.timeout}s"},
                execution_log=[],
                artifacts=[],
                usage={},
            )

        except Exception as e:
            await self.audit_logger.log_security_event(
                task_id, request.api_key, "execution_error", {"error": str(e)}
            )
            return AgenticTaskResponse(
                task_id=task_id,
                status="failed",
                result={"error": str(e)},
                execution_log=[],
                artifacts=[],
                usage={},
            )

        # Step 8: Extract usage data
        input_tokens = task_result.usage.get("input_tokens", 0) if task_result.usage else 0
        output_tokens = task_result.usage.get("output_tokens", 0) if task_result.usage else 0
        actual_cost = task_result.cost or 0.0

        # Check cost limit
        if actual_cost > request.max_cost:
            await self.audit_logger.log_security_event(
                task_id,
                request.api_key,
                "cost_exceeded",
                {"actual_cost": actual_cost, "max_cost": request.max_cost},
            )
            return AgenticTaskResponse(
                task_id=task_id,
                status="cost_exceeded",
                result={
                    "error": f"Cost ${actual_cost:.4f} exceeded limit ${request.max_cost:.4f}",
                    "output": task_result.completion[:500],  # Partial output
                },
                execution_log=[],
                artifacts=[],
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_cost": actual_cost,
                    "model_used": model,
                },
            )

        # Step 9: Track actual usage
        await self.budget_manager.track_usage(
            project_id=request.project_id,
            model=model,
            tokens=input_tokens + output_tokens,
            cost=actual_cost,
        )

        # Log successful completion
        await self.audit_logger.log_tool_call(
            task_id,
            request.api_key,
            "task_completed",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": actual_cost,
                "model": model,
            },
        )

        # Step 10: Parse execution log from output
        execution_log = self._parse_execution_log(task_result.completion)

        # Step 11: Collect artifacts from workspace
        artifacts = self._collect_artifacts(workspace_dir)

        # Step 12: Build response
        duration_seconds = time.time() - start_time

        return AgenticTaskResponse(
            task_id=task_id,
            status="completed",
            result={
                "summary": task_result.completion[:1000] if task_result.completion else "",
                "full_output": task_result.completion or "",
                "workspace_directory": str(workspace_dir),
            },
            execution_log=execution_log,
            artifacts=artifacts,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "total_cost": actual_cost,
                "model_used": model,
                "duration_seconds": round(duration_seconds, 2),
            },
        )

    def _validate_request(self, request: AgenticTaskRequest):
        """Validate request parameters."""
        if request.timeout > 600:
            raise ValueError("Timeout cannot exceed 600 seconds")

        if request.max_cost > 10.0:
            raise ValueError("Max cost cannot exceed $10.00")

        if not request.description:
            raise ValueError("Description is required")

        # Validate agents exist
        if request.allow_agents:
            agent_validation = self.agent_discovery.validate_agents(request.allow_agents)
            missing = [name for name, exists in agent_validation.items() if not exists]
            if missing:
                raise ValueError(f"Unknown agents requested: {', '.join(missing)}")

        # Validate skills exist
        if request.allow_skills:
            skill_validation = self.agent_discovery.validate_skills(request.allow_skills)
            missing = [name for name, exists in skill_validation.items() if not exists]
            if missing:
                raise ValueError(f"Unknown skills requested: {', '.join(missing)}")

    def _auto_select_model(self, request: AgenticTaskRequest) -> str:
        """
        Auto-select model based on task complexity.

        Agentic tasks default to sonnet (more complex than simple completions).
        """
        # Heuristic: if agents/skills requested, likely complex -> sonnet or opus
        if request.allow_agents or request.allow_skills:
            return "sonnet"

        # Otherwise, route based on description complexity
        return auto_select_model(
            prompt=request.description,
            context_size=len(request.description),
            budget_remaining=1000000,  # Assume sufficient budget for routing
        )

    def _estimate_tokens(self, request: AgenticTaskRequest, model: str) -> int:
        """
        Estimate token usage for agentic task.

        This is harder than simple completions due to multi-turn nature.
        Use conservative estimates.
        """
        # Base estimate from description length
        base_tokens = len(request.description.split()) * 1.5  # ~1.5 tokens per word

        # Add overhead for agentic features
        if request.allow_tools:
            base_tokens += 500  # Tool usage overhead

        if request.allow_agents:
            base_tokens += 2000  # Agent spawning overhead

        if request.allow_skills:
            base_tokens += 1000  # Skill invocation overhead

        # Multi-turn factor (agentic tasks often do 3-5 turns)
        multi_turn_factor = 3.0

        return int(base_tokens * multi_turn_factor)

    def _build_agentic_prompt(self, request: AgenticTaskRequest) -> str:
        """
        Build prompt with agentic configuration.

        This includes the task description plus metadata about allowed capabilities,
        including discovered agent/skill descriptions and invocation examples.
        """
        prompt_parts = [
            f"Task: {request.description}",
            "",
            "Configuration:",
            f"- Working Directory: {request.working_directory}",
        ]

        if request.allow_tools:
            prompt_parts.append(f"- Allowed Tools: {', '.join(request.allow_tools)}")

        # Add agent descriptions and invocation examples
        if request.allow_agents:
            agent_section = self.agent_discovery.build_agent_prompt_section(request.allow_agents)
            if agent_section:
                prompt_parts.append(agent_section)
            else:
                # Fallback if discovery fails
                prompt_parts.append(f"- Allowed Agents: {', '.join(request.allow_agents)}")

        # Add skill descriptions and invocation examples
        if request.allow_skills:
            skill_section = self.agent_discovery.build_skill_prompt_section(request.allow_skills)
            if skill_section:
                prompt_parts.append(skill_section)
            else:
                # Fallback if discovery fails
                prompt_parts.append(f"- Allowed Skills: {', '.join(request.allow_skills)}")

        prompt_parts.extend(
            [
                "",
                "Instructions:",
                "1. Complete the task using available tools, agents, and skills",
                "2. Use Task(subagent_type='agent-name', ...) to invoke agents",
                "3. Use Skill(command='skill-name') to invoke skills",
                "4. Be thorough and accurate",
                "5. Generate any requested artifacts in the working directory",
                "6. Provide a clear summary when done",
            ]
        )

        return "\n".join(prompt_parts)

    def _create_workspace(self, task_id: str) -> Path:
        """Create workspace directory for task artifacts."""
        workspace_dir = Path(f"/tmp/agentic_tasks/{task_id}")
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def _parse_execution_log(self, output: str) -> list[ExecutionLogEntry]:
        """
        Parse execution log from Claude's output.

        In a real implementation, this would parse Claude CLI's JSON output format
        to extract tool calls, agent spawns, etc.

        For now, create a simple log entry.
        """
        # TODO: Parse actual Claude CLI --output-format=json for detailed logs
        return [
            ExecutionLogEntry(
                step=1,
                timestamp=datetime.utcnow().isoformat(),
                action="task_completed",
                details={"output_length": len(output)},
            )
        ]

    def _collect_artifacts(self, workspace_dir: Path) -> list[Artifact]:
        """
        Collect generated artifacts from workspace directory.

        Args:
            workspace_dir: Path to workspace

        Returns:
            List of Artifact objects
        """
        artifacts = []

        if not workspace_dir.exists():
            return artifacts

        for file_path in workspace_dir.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                artifacts.append(
                    Artifact(
                        type="file",
                        path=str(file_path),
                        size_bytes=stat.st_size,
                        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    )
                )

        return artifacts
