"""API client wrapper for Claude Code API Service"""

from __future__ import annotations

from typing import Any

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout


class APIError(Exception):
    """API request error"""

    pass


class APIClient:
    """HTTP client for Claude Code API Service"""

    def __init__(self, base_url: str = "http://localhost:8006", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _handle_error(self, e: Exception, endpoint: str) -> None:
        """Handle request errors with helpful messages"""
        if isinstance(e, ConnectionError):
            raise APIError(
                f"Could not connect to service at {self.base_url}\n"
                f"  → Is the service running? Try: claude-api service start"
            )
        elif isinstance(e, Timeout):
            raise APIError(f"Request to {endpoint} timed out")
        elif isinstance(e, RequestException):
            raise APIError(f"Request failed: {str(e)}")
        else:
            raise APIError(f"Unexpected error: {str(e)}")

    def get(self, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make GET request"""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._handle_error(e, endpoint)

    def post(self, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make POST request"""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.post(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._handle_error(e, endpoint)

    def delete(self, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make DELETE request"""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.delete(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._handle_error(e, endpoint)

    def is_service_running(self) -> bool:
        """Check if service is running"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_health(self) -> dict[str, Any]:
        """Get service health"""
        return self.get("/health")

    def get_ready(self) -> dict[str, Any]:
        """Get service readiness status"""
        url = f"{self.base_url}/ready"
        try:
            response = self.session.get(url, timeout=3)
            return response.json()
        except Exception as e:
            self._handle_error(e, "/ready")

    def get_capabilities(self) -> dict[str, Any]:
        """Get agent/skill capabilities"""
        return self.get("/v1/capabilities")

    def chat_completion(self, model: str, messages: list, **kwargs) -> dict[str, Any]:
        """Create chat completion"""
        payload = {"model": model, "messages": messages, **kwargs}
        return self.post("/v1/chat/completions", json=payload)

    def create_task(
        self,
        description: str,
        allow_tools: list | None = None,
        allow_agents: list | None = None,
        allow_skills: list | None = None,
        timeout: int = 300,
        max_cost: float = 1.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Create agentic task"""
        payload = {"description": description, "timeout": timeout, "max_cost": max_cost, **kwargs}

        if allow_tools:
            payload["allow_tools"] = allow_tools
        if allow_agents:
            payload["allow_agents"] = allow_agents
        if allow_skills:
            payload["allow_skills"] = allow_skills

        return self.post("/v1/task", json=payload)

    def get_usage(self, project_id: str | None = None, period: str | None = None) -> dict[str, Any]:
        """Get usage statistics"""
        params = {}
        if project_id:
            params["project_id"] = project_id
        if period:
            params["period"] = period

        return self.get("/v1/usage", params=params)

    def process(
        self,
        provider: str = "anthropic",
        model_name: str = "haiku",
        user_message: str | None = None,
        system_message: str | None = None,
        messages: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
        use_cli: bool = False,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Send request via /v1/process endpoint"""
        payload: dict[str, Any] = {
            "provider": provider,
            "model_name": model_name,
            "use_cli": use_cli,
        }
        if user_message:
            payload["user_message"] = user_message
        if system_message:
            payload["system_message"] = system_message
        if messages:
            payload["messages"] = messages
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if project_id:
            payload["project_id"] = project_id

        return self.post("/v1/process", json=payload)

    def get_providers(self) -> list[dict[str, Any]]:
        """List available providers"""
        return self.get("/v1/providers")

    def get_provider_models(self, provider: str) -> dict[str, Any]:
        """Get models for a specific provider"""
        return self.get(f"/v1/providers/{provider}/models")

    def batch_process(
        self,
        prompts: list[dict[str, str]],
        model: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Process multiple prompts in parallel"""
        payload: dict[str, Any] = {"prompts": prompts, "timeout": timeout}
        if model:
            payload["model"] = model

        return self.post("/v1/batch", json=payload)

    def route_recommend(
        self,
        prompt: str,
        context_size: int = 0,
    ) -> dict[str, Any]:
        """Get model routing recommendation"""
        payload = {"prompt": prompt, "context_size": context_size}
        return self.post("/v1/route", json=payload)
