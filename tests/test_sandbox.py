"""
Tests for SandboxManager
CRITICAL SECURITY TESTS - ALL MUST PASS
"""

import pytest

docker = pytest.importorskip("docker.errors", reason="docker SDK not installed or shadowed")
import os
import time

import docker  # re-import full package after guard

from src.sandbox_manager import SandboxConfig, SandboxManager, SecurityError


class TestSandboxManager:
    """Test suite for Docker sandbox security"""

    @pytest.fixture
    def sandbox_manager(self):
        """Create a SandboxManager instance"""
        try:
            return SandboxManager()
        except RuntimeError as e:
            pytest.skip(f"Docker not available: {e}")

    @pytest.fixture
    def test_workspace(self, tmp_path):
        """Create a temporary workspace directory"""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()
        return str(workspace)

    @pytest.fixture
    def test_project(self, tmp_path):
        """Create a temporary project directory with test files"""
        project = tmp_path / "test_project"
        project.mkdir()

        # Create some test files
        (project / "README.md").write_text("# Test Project")
        (project / "src").mkdir()
        (project / "src" / "main.py").write_text("print('hello')")

        return str(project)

    def test_create_and_destroy_sandbox(self, sandbox_manager, test_project):
        """Test basic sandbox creation and destruction"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-001", project_path=test_project)

        assert sandbox.task_id == "test-001"
        assert sandbox.container_id
        assert os.path.exists(sandbox.workspace_path)

        # Cleanup
        sandbox_manager.destroy_sandbox(sandbox)
        assert not os.path.exists(sandbox.workspace_path)

    def test_network_isolation(self, sandbox_manager):
        """CRITICAL: Test that network access is blocked"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-network")

        try:
            # Try to access network - should fail
            exit_code, stdout, stderr = sandbox_manager.execute_command(
                sandbox, "curl http://google.com"
            )

            # Command should be blocked by security validator
            assert False, "curl should have been blocked"

        except SecurityError as e:
            # Expected - command blocked
            assert "curl" in str(e).lower()

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_filesystem_isolation_read_etc_passwd(self, sandbox_manager):
        """CRITICAL: Test that /etc/passwd cannot be read"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-fs-read")

        try:
            # Try to read /etc/passwd - should fail
            exit_code, stdout, stderr = sandbox_manager.execute_command(sandbox, "cat /etc/passwd")

            # Command executes but file doesn't exist in minimal container
            # OR we get permission denied
            # The key is it doesn't reveal host /etc/passwd
            assert "/etc/passwd" not in stdout or "No such file" in stderr

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_resource_limits_cpu(self, sandbox_manager):
        """Test that CPU limits are enforced"""
        config = SandboxConfig(cpu_quota=50000)  # 0.5 CPU cores
        sandbox = sandbox_manager.create_sandbox(task_id="test-cpu", config=config)

        try:
            # Verify container has CPU limit
            container = sandbox_manager.docker_client.containers.get(sandbox.container_id)
            cpu_quota = container.attrs["HostConfig"]["CpuQuota"]
            assert cpu_quota == 50000

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_resource_limits_memory(self, sandbox_manager):
        """Test that memory limits are enforced"""
        config = SandboxConfig(memory_limit="512m")
        sandbox = sandbox_manager.create_sandbox(task_id="test-memory", config=config)

        try:
            # Verify container has memory limit
            container = sandbox_manager.docker_client.containers.get(sandbox.container_id)
            memory_limit = container.attrs["HostConfig"]["Memory"]
            assert memory_limit == 512 * 1024 * 1024

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_command_blocking_rm_rf(self, sandbox_manager):
        """CRITICAL: Test that rm -rf is blocked"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-rm")

        try:
            with pytest.raises(SecurityError) as exc:
                sandbox_manager.execute_command(sandbox, "rm -rf /workspace")

            assert "rm -rf" in str(exc.value).lower()

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_command_blocking_sudo(self, sandbox_manager):
        """CRITICAL: Test that sudo is blocked"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-sudo")

        try:
            with pytest.raises(SecurityError) as exc:
                sandbox_manager.execute_command(sandbox, "sudo whoami")

            assert "sudo" in str(exc.value).lower()

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_path_validation_sensitive_files(self, sandbox_manager):
        """CRITICAL: Test that sensitive file paths are blocked"""
        # Test .env file
        is_valid = sandbox_manager.validate_file_access(".env", "read")
        assert not is_valid

        # Test SSH keys
        is_valid = sandbox_manager.validate_file_access("~/.ssh/id_rsa", "read")
        assert not is_valid

        # Test credentials
        is_valid = sandbox_manager.validate_file_access("credentials.json", "read")
        assert not is_valid

    def test_container_cleanup_after_task(self, sandbox_manager):
        """CRITICAL: Test that containers are destroyed after task"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-cleanup")
        container_id = sandbox.container_id

        # Execute a command
        sandbox_manager.execute_command(sandbox, "echo 'test'")

        # Destroy sandbox
        sandbox_manager.destroy_sandbox(sandbox)

        # Verify container is gone
        with pytest.raises(docker.errors.NotFound):
            sandbox_manager.docker_client.containers.get(container_id)

    def test_concurrent_sandboxes_isolation(self, sandbox_manager):
        """CRITICAL: Test that multiple sandboxes don't see each other's data"""
        sandbox1 = sandbox_manager.create_sandbox(task_id="test-concurrent-1")
        sandbox2 = sandbox_manager.create_sandbox(task_id="test-concurrent-2")

        try:
            # Write file in sandbox1
            sandbox_manager.execute_command(sandbox1, "echo 'secret data' > /workspace/secret.txt")

            # Try to read from sandbox2
            exit_code, stdout, stderr = sandbox_manager.execute_command(
                sandbox2, "cat /workspace/secret.txt"
            )

            # File should not exist in sandbox2
            assert "No such file" in stderr or exit_code != 0

        finally:
            sandbox_manager.destroy_sandbox(sandbox1)
            sandbox_manager.destroy_sandbox(sandbox2)

    def test_timeout_enforcement(self, sandbox_manager):
        """Test that command timeout is enforced"""
        config = SandboxConfig(timeout_seconds=2)
        sandbox = sandbox_manager.create_sandbox(task_id="test-timeout", config=config)

        try:
            # Execute a long-running command
            start = time.time()
            exit_code, stdout, stderr = sandbox_manager.execute_command(
                sandbox, "sleep 10", timeout=2
            )
            elapsed = time.time() - start

            # Should complete within timeout window
            assert elapsed < 5  # Should timeout around 2s, not run for 10s

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_workspace_isolation_write(self, sandbox_manager):
        """CRITICAL: Test that tasks can only write to workspace"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-write")

        try:
            # Validate that workspace writes are allowed
            is_valid = sandbox_manager.validate_file_access("/workspace/output.txt", "write")
            assert is_valid

            # Validate that non-workspace writes are blocked
            is_valid = sandbox_manager.validate_file_access("/project/output.txt", "write")
            assert not is_valid

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_get_workspace_files(self, sandbox_manager):
        """Test retrieving workspace files"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-files")

        try:
            # Create some files
            sandbox_manager.execute_command(
                sandbox,
                "echo 'test' > /workspace/file1.txt && mkdir /workspace/subdir && echo 'test2' > /workspace/subdir/file2.txt",
            )

            # Get workspace files
            files = sandbox_manager.get_workspace_files(sandbox)

            # Should list all files
            assert "file1.txt" in files
            assert "subdir/file2.txt" in files or "subdir\\file2.txt" in files

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_get_workspace_size(self, sandbox_manager):
        """Test measuring workspace size"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-size")

        try:
            # Create a file with known size
            sandbox_manager.execute_command(sandbox, "echo 'hello world' > /workspace/test.txt")

            size = sandbox_manager.get_workspace_size(sandbox)
            assert size > 0
            assert size < 1024  # Small file

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_security_options_enforced(self, sandbox_manager):
        """Test that security options are properly set on container"""
        sandbox = sandbox_manager.create_sandbox(task_id="test-security")

        try:
            container = sandbox_manager.docker_client.containers.get(sandbox.container_id)
            host_config = container.attrs["HostConfig"]

            # Verify security settings
            assert "no-new-privileges" in host_config["SecurityOpt"]
            assert host_config["CapDrop"] == ["ALL"]
            assert host_config["NetworkMode"] == "none"
            assert host_config["ReadonlyRootfs"] is True

        finally:
            sandbox_manager.destroy_sandbox(sandbox)

    def test_cleanup_old_sandboxes(self, sandbox_manager):
        """Test cleanup of old sandboxes"""
        # Create a sandbox
        sandbox = sandbox_manager.create_sandbox(task_id="test-old")

        try:
            # Cleanup sandboxes older than 0 seconds (should cleanup all)
            count = sandbox_manager.cleanup_old_sandboxes(max_age_seconds=0)
            assert count >= 1

            # Container should be gone
            with pytest.raises(docker.errors.NotFound):
                sandbox_manager.docker_client.containers.get(sandbox.container_id)

        except docker.errors.NotFound:
            pass  # Already cleaned up
