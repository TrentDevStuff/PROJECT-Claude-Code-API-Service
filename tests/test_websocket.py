"""
Tests for WebSocket streaming functionality.

Tests:
- WebSocket connection establishment
- Token streaming
- Error handling
- Multiple messages
- Budget checking
- Usage tracking
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from main import app
from src.budget_manager import BudgetManager
from src.websocket import WebSocketStreamer, initialize_websocket
from src.worker_pool import WorkerPool


@pytest.fixture
def mock_worker_pool():
    """Mock WorkerPool for testing."""
    pool = Mock(spec=WorkerPool)
    pool.running = True
    return pool


@pytest.fixture
def mock_budget_manager():
    """Mock BudgetManager for testing."""
    manager = AsyncMock(spec=BudgetManager)
    manager.check_budget = AsyncMock(return_value=True)
    manager.track_usage = AsyncMock()
    return manager


@pytest.fixture
def streamer(mock_worker_pool, mock_budget_manager):
    """Create WebSocketStreamer instance for testing."""
    return WebSocketStreamer(mock_worker_pool, mock_budget_manager)


class TestWebSocketConnection:
    """Test WebSocket connection handling."""

    @pytest.mark.asyncio
    async def test_websocket_connection(self, streamer):
        """Test successful WebSocket connection."""
        # Create mock WebSocket
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=asyncio.CancelledError()
        )  # Simulate disconnect

        # Handle connection (should not raise)
        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Verify connection was accepted
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_tracking(self, streamer):
        """Test that connections are tracked and cleaned up."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=asyncio.CancelledError())

        initial_count = len(streamer.active_connections)

        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Connection should be cleaned up
        assert len(streamer.active_connections) == initial_count


class TestStreamingResponse:
    """Test streaming response functionality."""

    @pytest.mark.asyncio
    async def test_streaming_response(self, streamer, mock_budget_manager):
        """Test streaming tokens to client."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        # Mock subprocess output
        mock_output = {
            "content": [{"text": "Hello world"}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

        with patch("subprocess.Popen") as mock_popen:
            # Mock process
            mock_process = MagicMock()
            mock_process.stdout = [json.dumps(mock_output)]
            mock_process.stderr = []
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            await streamer._stream_response(mock_ws, "Test prompt", "haiku", "test-project")

        # Verify tokens were sent
        calls = mock_ws.send_json.call_args_list

        # Should have token calls and a done call
        assert len(calls) > 0

        # Verify done message
        done_call = calls[-1]
        done_message = done_call[0][0]
        assert done_message["type"] == "done"
        assert "usage" in done_message
        assert "cost" in done_message

        # Verify usage tracking
        mock_budget_manager.track_usage.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_with_chunks(self, streamer, mock_budget_manager):
        """Test that content is streamed in chunks."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        # Create longer content that will be chunked
        long_text = "This is a longer response " * 20  # ~140 chars
        mock_output = {
            "content": [{"text": long_text}],
            "usage": {"input_tokens": 10, "output_tokens": 50, "total_tokens": 60},
        }

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = [json.dumps(mock_output)]
            mock_process.stderr = []
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            await streamer._stream_response(mock_ws, "Test prompt", "haiku", "test-project")

        # Verify multiple token chunks were sent
        calls = mock_ws.send_json.call_args_list
        token_calls = [c for c in calls if c[0][0].get("type") == "token"]

        # Should have multiple chunks (at least 5 for this length)
        assert len(token_calls) >= 5

        # Reconstruct full text from chunks
        reconstructed = "".join([c[0][0]["content"] for c in token_calls])
        assert reconstructed == long_text


class TestWebSocketErrorHandling:
    """Test error handling in WebSocket connections."""

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, streamer):
        """Test error handling for malformed messages."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # Send invalid JSON, then disconnect
        mock_ws.receive_text = AsyncMock(side_effect=["invalid json", asyncio.CancelledError()])

        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Verify error was sent
        error_calls = [
            c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "Invalid JSON" in error_calls[0][0][0]["error"]

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, streamer):
        """Test handling of unknown message types."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        message = json.dumps({"type": "unknown"})
        mock_ws.receive_text = AsyncMock(side_effect=[message, asyncio.CancelledError()])

        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Verify error was sent
        error_calls = [
            c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "Unknown message type" in error_calls[0][0][0]["error"]

    @pytest.mark.asyncio
    async def test_budget_exceeded_error(self, streamer, mock_budget_manager):
        """Test error when budget is exceeded."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # Mock budget check to fail
        mock_budget_manager.check_budget = AsyncMock(return_value=False)

        message = json.dumps(
            {"type": "chat", "model": "haiku", "messages": [{"role": "user", "content": "Hello"}]}
        )

        mock_ws.receive_text = AsyncMock(side_effect=[message, asyncio.CancelledError()])

        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Verify budget error was sent
        error_calls = [
            c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "Budget exceeded" in error_calls[0][0][0]["error"]

    @pytest.mark.asyncio
    async def test_invalid_model_error(self, streamer):
        """Test error for invalid model."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        message = json.dumps(
            {
                "type": "chat",
                "model": "invalid-model",
                "messages": [{"role": "user", "content": "Hello"}],
            }
        )

        mock_ws.receive_text = AsyncMock(side_effect=[message, asyncio.CancelledError()])

        try:
            await streamer.handle_connection(mock_ws)
        except asyncio.CancelledError:
            pass

        # Verify invalid model error was sent
        error_calls = [
            c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "Invalid model" in error_calls[0][0][0]["error"]

    @pytest.mark.asyncio
    async def test_subprocess_error(self, streamer, mock_budget_manager):
        """Test handling of subprocess errors."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        with patch("subprocess.Popen") as mock_popen:
            # Mock process that exits with error
            mock_process = MagicMock()
            mock_process.stdout = []
            mock_process.stderr = ["Error message"]
            mock_process.wait.return_value = 1  # Non-zero exit code
            mock_popen.return_value = mock_process

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="exited with code 1"):
                await streamer._stream_response(mock_ws, "Test prompt", "haiku", "test-project")


class TestMultipleMessages:
    """Test handling multiple messages on same connection."""

    @pytest.mark.asyncio
    async def test_multiple_messages(self, streamer, mock_budget_manager):
        """Test handling multiple chat messages on same connection."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # Two chat messages, then disconnect
        message1 = json.dumps(
            {
                "type": "chat",
                "model": "haiku",
                "messages": [{"role": "user", "content": "First message"}],
            }
        )

        message2 = json.dumps(
            {
                "type": "chat",
                "model": "haiku",
                "messages": [{"role": "user", "content": "Second message"}],
            }
        )

        mock_output = {
            "content": [{"text": "Response"}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

        messages_received = 0

        async def receive_side_effect():
            nonlocal messages_received
            if messages_received == 0:
                messages_received += 1
                return message1
            elif messages_received == 1:
                messages_received += 1
                return message2
            else:
                raise asyncio.CancelledError()

        mock_ws.receive_text = AsyncMock(side_effect=receive_side_effect)

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = [json.dumps(mock_output)]
            mock_process.stderr = []
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            try:
                await streamer.handle_connection(mock_ws)
            except asyncio.CancelledError:
                pass

        # Verify usage was tracked twice
        assert mock_budget_manager.track_usage.call_count == 2


class TestCostCalculation:
    """Test cost calculation."""

    def test_calculate_cost_haiku(self, streamer):
        """Test cost calculation for Haiku."""
        cost = streamer._calculate_cost("haiku", 1000, 500)

        # Haiku: $0.25/MTk input, $1.25/MTk output
        expected = (1000 / 1_000_000) * 0.25 + (500 / 1_000_000) * 1.25
        assert abs(cost - expected) < 0.0001

    def test_calculate_cost_sonnet(self, streamer):
        """Test cost calculation for Sonnet."""
        cost = streamer._calculate_cost("sonnet", 1000, 500)

        # Sonnet: $3.00/MTk input, $15.00/MTk output
        expected = (1000 / 1_000_000) * 3.00 + (500 / 1_000_000) * 15.00
        assert abs(cost - expected) < 0.0001

    def test_calculate_cost_opus(self, streamer):
        """Test cost calculation for Opus."""
        cost = streamer._calculate_cost("opus", 1000, 500)

        # Opus: $15.00/MTk input, $75.00/MTk output
        expected = (1000 / 1_000_000) * 15.00 + (500 / 1_000_000) * 75.00
        assert abs(cost - expected) < 0.0001

    def test_calculate_cost_unknown_model(self, streamer):
        """Test cost calculation for unknown model."""
        cost = streamer._calculate_cost("unknown", 1000, 500)
        assert cost == 0.0


@pytest.mark.integration
class TestWebSocketIntegration:
    """Integration tests with actual FastAPI TestClient."""

    def test_websocket_endpoint_exists(self):
        """Test that WebSocket endpoint is registered."""
        # Initialize services
        from src.budget_manager import BudgetManager
        from src.worker_pool import WorkerPool

        worker_pool = WorkerPool(max_workers=1)
        budget_manager = BudgetManager(db_path=":memory:")

        initialize_websocket(worker_pool, budget_manager)

        # Test client
        client = TestClient(app)

        # WebSocket endpoint should be accessible
        # Note: TestClient doesn't support WebSocket testing well,
        # but we can verify the route exists
        assert "/v1/stream" in [route.path for route in app.routes]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
