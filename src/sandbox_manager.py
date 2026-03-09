"""
Sandbox Manager
Creates and manages isolated Docker containers for secure agentic task execution
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import docker

logger = logging.getLogger(__name__)

from .security_validator import SecurityValidator


@dataclass
class SandboxConfig:
    """Configuration for a sandbox environment"""

    cpu_quota: int = 100000  # 1 CPU core (100000 = 100%)
    memory_limit: str = "1g"  # 1GB RAM
    memory_swap_limit: str = "1g"  # 1GB swap (total = 2GB)
    pids_limit: int = 100  # Max 100 processes
    workspace_size_mb: int = 100  # 100MB workspace
    timeout_seconds: int = 300  # 5 minute timeout
    network_enabled: bool = False  # No network by default


@dataclass
class Sandbox:
    """Represents an active sandbox environment"""

    task_id: str
    container_id: str
    workspace_path: str
    project_path: str | None
    config: SandboxConfig
    created_at: float


class SandboxManager:
    """Manages Docker-based sandboxes for secure task execution"""

    SANDBOX_IMAGE = "claude-code-sandbox:latest"
    CONTAINER_WORKSPACE = "/workspace"
    CONTAINER_PROJECT = "/project"

    def __init__(self):
        """Initialize the sandbox manager"""
        try:
            self.docker_client = docker.from_env()
            self.validator = SecurityValidator()
            self._ensure_sandbox_image()
        except docker.errors.DockerException as e:
            raise RuntimeError(f"Failed to connect to Docker: {e}")

    def _ensure_sandbox_image(self):
        """Ensure the sandbox Docker image exists"""
        try:
            self.docker_client.images.get(self.SANDBOX_IMAGE)
        except docker.errors.ImageNotFound:
            # Build the image from Dockerfile
            dockerfile_path = Path(__file__).parent.parent / "docker-build"
            try:
                logger.info("Building sandbox image from %s", dockerfile_path)
                self.docker_client.images.build(
                    path=str(dockerfile_path),
                    dockerfile="Dockerfile.sandbox",
                    tag=self.SANDBOX_IMAGE,
                    rm=True,
                )
                logger.info("Sandbox image %s built successfully", self.SANDBOX_IMAGE)
            except Exception as e:
                raise RuntimeError(f"Failed to build sandbox image: {e}")

    def create_sandbox(
        self,
        task_id: str,
        project_path: str | None = None,
        config: SandboxConfig | None = None,
    ) -> Sandbox:
        """
        Create an isolated Docker sandbox for a task

        Args:
            task_id: Unique identifier for the task
            project_path: Optional path to project files (mounted read-only)
            config: Optional sandbox configuration (uses defaults if not provided)

        Returns:
            Sandbox object representing the active sandbox

        Raises:
            RuntimeError: If sandbox creation fails
        """
        if config is None:
            config = SandboxConfig()

        # Create temporary workspace directory
        workspace_path = tempfile.mkdtemp(prefix=f"sandbox-{task_id}-")

        try:
            # Prepare volume mounts
            volumes = {workspace_path: {"bind": self.CONTAINER_WORKSPACE, "mode": "rw"}}

            # Mount project files read-only if provided
            if project_path:
                volumes[project_path] = {"bind": self.CONTAINER_PROJECT, "mode": "ro"}

            # Create tmpfs for /tmp with noexec, nosuid
            tmpfs = {"/tmp": f"rw,noexec,nosuid,size={config.workspace_size_mb}m"}

            # Configure network mode
            network_mode = "none" if not config.network_enabled else "bridge"

            # Create and start container
            container = self.docker_client.containers.run(
                self.SANDBOX_IMAGE,
                detach=True,
                remove=False,  # We'll remove manually after cleanup
                network_mode=network_mode,
                read_only=True,  # Root filesystem is read-only
                security_opt=["no-new-privileges"],  # Prevent privilege escalation
                cap_drop=["ALL"],  # Drop all capabilities
                cpu_quota=config.cpu_quota,
                mem_limit=config.memory_limit,
                memswap_limit=config.memory_swap_limit,
                pids_limit=config.pids_limit,
                volumes=volumes,
                tmpfs=tmpfs,
                # Start in sleep mode - we'll exec commands into it
                command="sleep infinity",
                labels={"task_id": task_id, "managed_by": "claude-code-api"},
            )

            return Sandbox(
                task_id=task_id,
                container_id=container.id,
                workspace_path=workspace_path,
                project_path=project_path,
                config=config,
                created_at=time.time(),
            )

        except Exception as e:
            # Cleanup workspace on failure
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise RuntimeError(f"Failed to create sandbox: {e}")

    def execute_command(
        self, sandbox: Sandbox, command: str, timeout: int | None = None
    ) -> tuple[int, str, str]:
        """
        Execute a command inside the sandbox with security validation

        Args:
            sandbox: Active sandbox to execute in
            command: Command to execute
            timeout: Optional timeout in seconds (uses sandbox config if not provided)

        Returns:
            Tuple of (exit_code, stdout, stderr)

        Raises:
            SecurityError: If command fails security validation
            RuntimeError: If execution fails
        """
        # Validate command security
        is_valid, error_msg = self.validator.validate_command(command)
        if not is_valid:
            raise SecurityError(f"Command blocked: {error_msg}")

        if timeout is None:
            timeout = sandbox.config.timeout_seconds

        try:
            container = self.docker_client.containers.get(sandbox.container_id)

            # Execute command
            exit_code, output = container.exec_run(
                f"/bin/bash -c '{command}'",
                demux=True,
                user="claude",
                workdir=self.CONTAINER_WORKSPACE,
            )

            # Demux output
            stdout = output[0].decode("utf-8") if output[0] else ""
            stderr = output[1].decode("utf-8") if output[1] else ""

            return exit_code, stdout, stderr

        except docker.errors.NotFound:
            raise RuntimeError(f"Sandbox container not found: {sandbox.container_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {e}")

    def validate_file_access(self, path: str, operation: str = "read") -> bool:
        """
        Validate if file access is allowed

        Args:
            path: File path to validate
            operation: "read" or "write"

        Returns:
            True if access is allowed, False otherwise
        """
        allow_write = operation == "write"
        is_valid, _ = self.validator.validate_path(path, allow_write=allow_write)
        return is_valid

    def get_workspace_files(self, sandbox: Sandbox) -> list[str]:
        """
        Get list of files in the sandbox workspace

        Args:
            sandbox: Active sandbox

        Returns:
            List of file paths relative to workspace
        """
        files = []
        workspace = Path(sandbox.workspace_path)

        for path in workspace.rglob("*"):
            if path.is_file():
                relative = path.relative_to(workspace)
                files.append(str(relative))

        return files

    def get_workspace_size(self, sandbox: Sandbox) -> int:
        """
        Get total size of workspace in bytes

        Args:
            sandbox: Active sandbox

        Returns:
            Total size in bytes
        """
        total_size = 0
        workspace = Path(sandbox.workspace_path)

        for path in workspace.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size

        return total_size

    def destroy_sandbox(self, sandbox: Sandbox, force: bool = False):
        """
        Destroy a sandbox and clean up all resources

        Args:
            sandbox: Sandbox to destroy
            force: If True, force remove container even if running

        Raises:
            RuntimeError: If cleanup fails
        """
        try:
            # Stop and remove container
            try:
                container = self.docker_client.containers.get(sandbox.container_id)
                container.stop(timeout=5)
                container.remove(force=force)
            except docker.errors.NotFound:
                pass  # Container already gone
            except Exception as e:
                if not force:
                    raise RuntimeError(f"Failed to remove container: {e}")

            # Remove workspace directory
            if os.path.exists(sandbox.workspace_path):
                shutil.rmtree(sandbox.workspace_path, ignore_errors=True)

        except Exception as e:
            raise RuntimeError(f"Failed to destroy sandbox: {e}")

    def cleanup_old_sandboxes(self, max_age_seconds: int = 3600):
        """
        Clean up sandboxes older than max_age_seconds

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of sandboxes cleaned up
        """
        count = 0
        try:
            # Find all containers managed by this service
            containers = self.docker_client.containers.list(
                all=True, filters={"label": "managed_by=claude-code-api"}
            )

            current_time = time.time()
            for container in containers:
                # Check container age
                created = container.attrs["Created"]
                # Parse ISO 8601 timestamp
                import datetime

                created_dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                created_timestamp = created_dt.timestamp()

                age = current_time - created_timestamp
                if age > max_age_seconds:
                    container.stop(timeout=5)
                    container.remove(force=True)
                    count += 1

        except Exception as e:
            logger.warning("Sandbox cleanup failed: %s", e)

        return count


class SecurityError(Exception):
    """Raised when a security validation fails"""

    pass
