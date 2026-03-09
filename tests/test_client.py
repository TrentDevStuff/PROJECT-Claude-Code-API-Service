"""
Tests for Claude API Client Library

Comprehensive tests for both synchronous and asynchronous client operations.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from client import (
    AsyncClaudeClient,
    AuthenticationError,
    BatchResponse,
    BudgetExceededError,
    ClaudeClient,
    Model,
    RateLimitError,
    Response,
    UsageStats,
)
from client import (
    TimeoutError as ClientTimeoutError,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_response_data():
    """Sample response data from API."""
    return {
        "id": "task-123",
        "model": "sonnet",
        "content": "This is a test response",
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        "cost": 0.0015,
        "project_id": "test-project",
    }


@pytest.fixture
def mock_batch_response_data():
    """Sample batch response data from API."""
    return {
        "total": 3,
        "completed": 2,
        "failed": 1,
        "results": [
            {
                "id": "0",
                "prompt": "Hello",
                "status": "completed",
                "content": "Hi there!",
                "usage": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
                "cost": 0.0005,
            },
            {
                "id": "1",
                "prompt": "Count to 5",
                "status": "completed",
                "content": "1, 2, 3, 4, 5",
                "usage": {"input_tokens": 8, "output_tokens": 12, "total_tokens": 20},
                "cost": 0.0007,
            },
            {"id": "2", "prompt": "Error prompt", "status": "failed", "error": "Task timeout"},
        ],
        "total_cost": 0.0012,
        "total_tokens": 35,
    }


@pytest.fixture
def mock_usage_data():
    """Sample usage statistics data from API."""
    return {
        "project_id": "test-project",
        "period": "month",
        "total_tokens": 1000,
        "total_cost": 0.05,
        "by_model": {
            "haiku": {"tokens": 500, "cost": 0.01},
            "sonnet": {"tokens": 500, "cost": 0.04},
        },
        "limit": 10000,
        "remaining": 9000,
    }


# ============================================================================
# Synchronous Client Tests
# ============================================================================


class TestClaudeClient:
    """Tests for synchronous ClaudeClient."""

    def test_client_initialization(self):
        """Test client initialization with default and custom parameters."""
        # Default initialization
        client = ClaudeClient()
        assert client.base_url == "http://localhost:8080"
        assert client.project_id == "default"
        assert client.timeout == 30.0
        assert client.max_retries == 3

        # Custom initialization
        client = ClaudeClient(
            base_url="http://example.com:8000",
            api_key="test-key",
            project_id="my-project",
            timeout=60.0,
            max_retries=5,
        )
        assert client.base_url == "http://example.com:8000"
        assert client.api_key == "test-key"
        assert client.project_id == "my-project"
        assert client.timeout == 60.0
        assert client.max_retries == 5

        client.close()

    def test_context_manager(self):
        """Test client works as context manager."""
        with ClaudeClient() as client:
            assert client.client is not None

    @patch("httpx.Client.request")
    def test_client_complete(self, mock_request, mock_response_data):
        """Test successful completion request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            response = client.complete("Test prompt")

            # Verify response
            assert isinstance(response, Response)
            assert response.id == "task-123"
            assert response.model == "sonnet"
            assert response.content == "This is a test response"
            assert response.usage.input_tokens == 10
            assert response.usage.output_tokens == 20
            assert response.usage.total_tokens == 30
            assert response.cost == 0.0015

            # Verify request was made correctly
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/v1/chat/completions"

    @patch("httpx.Client.request")
    def test_client_complete_with_model(self, mock_request, mock_response_data):
        """Test completion with explicit model selection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            response = client.complete("Test prompt", model=Model.HAIKU)

            # Verify model was included in request
            call_args = mock_request.call_args
            request_data = call_args[1]["json"]
            assert request_data["model"] == "haiku"

    @patch("httpx.Client.request")
    def test_client_stream(self, mock_request, mock_response_data):
        """Test streaming (currently falls back to complete)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            chunks = list(client.stream("Test prompt"))

            # Should yield full response
            assert len(chunks) == 1
            assert chunks[0] == "This is a test response"

    @patch("httpx.Client.request")
    def test_client_batch(self, mock_request, mock_batch_response_data):
        """Test batch processing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_batch_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            prompts = ["Hello", "Count to 5", "Error prompt"]
            results = client.batch(prompts, model="haiku")

            # Verify response
            assert isinstance(results, BatchResponse)
            assert results.total == 3
            assert results.completed == 2
            assert results.failed == 1
            assert results.total_cost == 0.0012
            assert results.total_tokens == 35
            assert len(results.results) == 3

            # Check individual results
            assert results.results[0].status == "completed"
            assert results.results[0].content == "Hi there!"
            assert results.results[2].status == "failed"
            assert results.results[2].error == "Task timeout"

    @patch("httpx.Client.request")
    def test_client_get_usage(self, mock_request, mock_usage_data):
        """Test usage statistics retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_usage_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            stats = client.get_usage(period="month")

            # Verify response
            assert isinstance(stats, UsageStats)
            assert stats.project_id == "test-project"
            assert stats.period == "month"
            assert stats.total_tokens == 1000
            assert stats.total_cost == 0.05
            assert stats.limit == 10000
            assert stats.remaining == 9000
            assert "haiku" in stats.by_model
            assert "sonnet" in stats.by_model

    @patch("httpx.Client.request")
    def test_client_health(self, mock_request):
        """Test health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "version": "0.1.0",
            "services": {"worker_pool": "running"},
        }
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            health = client.health()

            assert health["status"] == "ok"
            assert health["version"] == "0.1.0"

    @patch("httpx.Client.request")
    def test_error_handling_authentication(self, mock_request):
        """Test authentication error handling."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Unauthorized"}
        mock_request.return_value = mock_response

        with ClaudeClient() as client, pytest.raises(AuthenticationError):
            client.complete("Test prompt")

    @patch("httpx.Client.request")
    def test_error_handling_budget_exceeded(self, mock_request):
        """Test budget exceeded error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"detail": "Budget exceeded for project test"}
        mock_request.return_value = mock_response

        with ClaudeClient() as client, pytest.raises(BudgetExceededError):
            client.complete("Test prompt")

    @patch("httpx.Client.request")
    def test_error_handling_rate_limit(self, mock_request):
        """Test rate limit error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"detail": "Too many requests"}
        mock_request.return_value = mock_response

        with ClaudeClient() as client, pytest.raises(RateLimitError):
            client.complete("Test prompt")

    @patch("httpx.Client.request")
    @patch("time.sleep")
    def test_retry_logic(self, mock_sleep, mock_request, mock_response_data):
        """Test automatic retry on server errors."""
        # First two calls fail, third succeeds
        mock_response_error = Mock()
        mock_response_error.status_code = 500
        mock_response_error.json.return_value = {"detail": "Server error"}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = mock_response_data
        mock_response_success.raise_for_status = Mock()

        mock_request.side_effect = [mock_response_error, mock_response_error, mock_response_success]

        with ClaudeClient(max_retries=3) as client:
            response = client.complete("Test prompt")

            # Should succeed after retries
            assert response.content == "This is a test response"

            # Should have retried
            assert mock_request.call_count == 3
            assert mock_sleep.call_count == 2

    @patch("httpx.Client.request")
    def test_timeout_error(self, mock_request):
        """Test timeout error handling."""
        mock_request.side_effect = httpx.TimeoutException("Request timeout")

        with ClaudeClient(max_retries=1) as client, pytest.raises(ClientTimeoutError):
            client.complete("Test prompt")


# ============================================================================
# Asynchronous Client Tests
# ============================================================================


class TestAsyncClaudeClient:
    """Tests for asynchronous AsyncClaudeClient."""

    @pytest.mark.asyncio
    async def test_async_client_initialization(self):
        """Test async client initialization."""
        client = AsyncClaudeClient()
        assert client.base_url == "http://localhost:8080"
        assert client.project_id == "default"
        await client.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async client works as context manager."""
        async with AsyncClaudeClient() as client:
            assert client.client is not None

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_async_client_complete(self, mock_request, mock_response_data):
        """Test async completion request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        async with AsyncClaudeClient() as client:
            response = await client.complete("Test prompt")

            # Verify response
            assert isinstance(response, Response)
            assert response.id == "task-123"
            assert response.content == "This is a test response"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_async_client_stream(self, mock_request, mock_response_data):
        """Test async streaming."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        async with AsyncClaudeClient() as client:
            chunks = []
            async for chunk in client.stream("Test prompt"):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0] == "This is a test response"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_async_client_batch(self, mock_request, mock_batch_response_data):
        """Test async batch processing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_batch_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        async with AsyncClaudeClient() as client:
            prompts = ["Hello", "Count to 5", "Error prompt"]
            results = await client.batch(prompts)

            assert results.total == 3
            assert results.completed == 2
            assert results.failed == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_async_client_get_usage(self, mock_request, mock_usage_data):
        """Test async usage statistics retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_usage_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        async with AsyncClaudeClient() as client:
            stats = await client.get_usage(period="week")

            assert stats.project_id == "test-project"
            assert stats.total_tokens == 1000

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_async_error_handling(self, mock_request):
        """Test async error handling."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Unauthorized"}
        mock_request.return_value = mock_response

        async with AsyncClaudeClient() as client:
            with pytest.raises(AuthenticationError):
                await client.complete("Test prompt")

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_async_retry_logic(self, mock_sleep, mock_request, mock_response_data):
        """Test async automatic retry logic."""
        mock_response_error = Mock()
        mock_response_error.status_code = 500

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = mock_response_data
        mock_response_success.raise_for_status = Mock()

        mock_request.side_effect = [mock_response_error, mock_response_success]

        async with AsyncClaudeClient(max_retries=3) as client:
            response = await client.complete("Test prompt")

            assert response.content == "This is a test response"
            assert mock_request.call_count == 2
            assert mock_sleep.call_count == 1


# ============================================================================
# Integration-like Tests (without real API)
# ============================================================================


class TestClientIntegration:
    """Integration-style tests."""

    @patch("httpx.Client.request")
    def test_multiple_requests_same_client(self, mock_request, mock_response_data):
        """Test making multiple requests with same client instance."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with ClaudeClient() as client:
            # Multiple completions
            response1 = client.complete("Prompt 1")
            response2 = client.complete("Prompt 2", model="haiku")
            response3 = client.complete("Prompt 3", project_id="other-project")

            assert response1.content == "This is a test response"
            assert response2.content == "This is a test response"
            assert response3.content == "This is a test response"
            assert mock_request.call_count == 3

    @patch("httpx.Client.request")
    def test_mixed_operations(self, mock_request, mock_response_data, mock_usage_data):
        """Test mixing different types of operations."""

        # Return different responses based on endpoint
        def mock_request_side_effect(method, endpoint, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/usage" in endpoint:
                mock_response.json.return_value = mock_usage_data
            elif "/health" in endpoint:
                mock_response.json.return_value = {"status": "ok"}
            else:
                mock_response.json.return_value = mock_response_data

            return mock_response

        mock_request.side_effect = mock_request_side_effect

        with ClaudeClient() as client:
            # Health check
            health = client.health()
            assert health["status"] == "ok"

            # Completion
            response = client.complete("Test")
            assert response.content == "This is a test response"

            # Usage stats
            stats = client.get_usage()
            assert stats.total_tokens == 1000
