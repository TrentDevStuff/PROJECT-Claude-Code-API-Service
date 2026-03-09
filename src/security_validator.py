"""
Security Validator
Validates commands and file paths to prevent malicious operations
"""

import os


class SecurityValidator:
    """Validates commands and file paths against security policies"""

    # Dangerous commands that must be blocked
    DANGEROUS_COMMANDS = [
        "rm -rf",
        "dd if=",
        "mkfs",
        "format",
        "curl",
        "wget",
        "nc",
        "netcat",
        "telnet",
        "ssh",
        "scp",
        "ftp",
        "sudo",
        "su",
        "chmod +s",
        "chown",
        ":(){ :|:& };:",  # Fork bomb
        "> /dev/",  # Device access
        "iptables",
        "ufw",
        "firewall",
    ]

    # Sensitive file paths that must be blocked
    SENSITIVE_PATHS = [
        "/etc/passwd",
        "/etc/shadow",
        "/etc/group",
        "/etc/sudoers",
        "/root/",
        "/home/",
        "~/.ssh/",
        ".ssh/",
        ".env",
        "credentials.json",
        "secrets.yaml",
        "secrets.yml",
        ".pem",
        ".key",
        ".crt",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "api_key",
        "access_token",
        "secret_key",
        ".aws/",
        ".kube/",
        ".docker/config.json",
    ]

    # Allowed workspace prefix - only files under this can be written
    WORKSPACE_PREFIX = "/workspace/"
    PROJECT_PREFIX = "/project/"

    def validate_command(self, cmd: str) -> tuple[bool, str]:
        """
        Validate a bash command for security

        Args:
            cmd: Command string to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if command is allowed
            - (False, "reason") if command is blocked
        """
        cmd_lower = cmd.lower()

        # Check for dangerous commands
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous.lower() in cmd_lower:
                return False, f"Dangerous command blocked: {dangerous}"

        # Block pipe to network devices
        if "|" in cmd and any(net in cmd_lower for net in ["curl", "wget", "nc", "telnet"]):
            return False, "Piping to network commands is blocked"

        # Block background processes that might persist
        if "&" in cmd and not cmd.strip().endswith("&"):
            return False, "Background processes must end with '&'"

        # Block redirects to sensitive locations
        if (">" in cmd or ">>" in cmd) and any(
            sensitive in cmd_lower for sensitive in ["/etc/", "/root/", "/home/", "/dev/"]
        ):
            return False, "Redirect to sensitive location blocked"

        return True, ""

    def validate_path(self, path: str, allow_write: bool = False) -> tuple[bool, str]:
        """
        Validate a file path for security

        Args:
            path: File path to validate
            allow_write: If True, check write permissions; if False, check read permissions

        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if path is allowed
            - (False, "reason") if path is blocked
        """
        # Normalize path
        normalized = os.path.normpath(path)

        # Check for sensitive paths
        for sensitive in self.SENSITIVE_PATHS:
            if sensitive in normalized or normalized.endswith(sensitive):
                return False, f"Access to sensitive path blocked: {sensitive}"

        # Check for path traversal attempts
        if ".." in path:
            return False, "Path traversal (..) is not allowed"

        # For write operations, must be in workspace
        if allow_write:
            if not normalized.startswith(self.WORKSPACE_PREFIX):
                return False, f"Write access only allowed in {self.WORKSPACE_PREFIX}"

        # For read operations, must be in workspace or project (read-only)
        else:
            if not (
                normalized.startswith(self.WORKSPACE_PREFIX)
                or normalized.startswith(self.PROJECT_PREFIX)
            ):
                return (
                    False,
                    f"Read access only allowed in {self.WORKSPACE_PREFIX} or {self.PROJECT_PREFIX}",
                )

        return True, ""

    def sanitize_environment(self, env: dict) -> dict:
        """
        Sanitize environment variables to remove sensitive data

        Args:
            env: Environment dictionary

        Returns:
            Sanitized environment dictionary
        """
        # Keys to remove (case-insensitive)
        sensitive_keys = {
            "API_KEY",
            "SECRET_KEY",
            "ACCESS_TOKEN",
            "PASSWORD",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "ANTHROPIC_API_KEY",
        }

        sanitized = {}
        for key, value in env.items():
            key_upper = key.upper()
            if not any(sensitive in key_upper for sensitive in sensitive_keys):
                sanitized[key] = value

        return sanitized

    def get_allowed_commands(self) -> list[str]:
        """Get list of explicitly allowed safe commands"""
        return [
            "ls",
            "cat",
            "head",
            "tail",
            "grep",
            "find",
            "echo",
            "pwd",
            "cd",
            "mkdir",
            "touch",
            "cp",
            "mv",
            "python",
            "python3",
            "pip",
            "pytest",
            "git status",
            "git log",
            "git diff",
            "wc",
            "sort",
            "uniq",
            "cut",
            "awk",
            "sed",
        ]
