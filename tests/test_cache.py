"""
Tests for Redis cache and queue functionality.

Tests cover:
- Cache storage and retrieval
- Cache expiration (TTL)
- Queue operations (FIFO)
- Connection error handling
- Edge cases
"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from src.cache import RedisCache


# Fixtures
@pytest.fixture
def mock_redis():
    """Create a mock Redis client that simulates basic operations."""
    mock = MagicMock()
    mock.ping.return_value = True

    # Simulate in-memory storage
    mock._storage = {}
    mock._expiry = {}
    mock._queue = []

    def mock_setex(key, ttl, value):
        mock._storage[key] = value
        mock._expiry[key] = time.time() + ttl
        return True

    def mock_get(key):
        if key not in mock._storage:
            return None
        if key in mock._expiry and time.time() > mock._expiry[key]:
            del mock._storage[key]
            del mock._expiry[key]
            return None
        return mock._storage[key]

    def mock_rpush(key, value):
        mock._queue.append(value)
        return len(mock._queue)

    def mock_lpop(key):
        if not mock._queue:
            return None
        return mock._queue.pop(0)

    def mock_llen(key):
        return len(mock._queue)

    def mock_keys(pattern):
        return [k for k in mock._storage if pattern.replace("*", "") in k]

    def mock_delete(*keys):
        for key in keys:
            mock._storage.pop(key, None)
            mock._expiry.pop(key, None)
            # Clear queue if queue key is deleted
            if key == "queue:requests":
                mock._queue.clear()
        return len(keys)

    mock.setex = mock_setex
    mock.get = mock_get
    mock.rpush = mock_rpush
    mock.lpop = mock_lpop
    mock.llen = mock_llen
    mock.keys = mock_keys
    mock.delete = mock_delete

    return mock


@pytest.fixture
def cache_with_mock(mock_redis):
    """Create a RedisCache instance with mocked Redis client."""
    with patch("redis.Redis", return_value=mock_redis):
        cache = RedisCache()
        return cache


@pytest.fixture
def cache_disconnected():
    """Create a RedisCache instance that fails to connect."""
    with patch("redis.Redis") as mock_redis_class:
        mock_client = Mock()
        mock_client.ping.side_effect = RedisConnectionError("Connection refused")
        mock_redis_class.return_value = mock_client

        cache = RedisCache()
        return cache


# Test: Cache and Retrieve
def test_cache_and_retrieve(cache_with_mock):
    """Test basic cache storage and retrieval."""
    prompt_hash = "abc123"
    response = {
        "completion": "Hello, world!",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "cost": 0.001,
    }

    # Cache the response
    success = cache_with_mock.cache_response(prompt_hash, response, ttl=3600)
    assert success is True

    # Retrieve the cached response
    cached = cache_with_mock.get_cached_response(prompt_hash)
    assert cached is not None
    assert cached == response
    assert cached["completion"] == "Hello, world!"


def test_cache_miss(cache_with_mock):
    """Test cache miss returns None."""
    result = cache_with_mock.get_cached_response("nonexistent")
    assert result is None


def test_cache_overwrite(cache_with_mock):
    """Test that caching with same key overwrites previous value."""
    prompt_hash = "test_key"

    response1 = {"data": "first"}
    cache_with_mock.cache_response(prompt_hash, response1)

    response2 = {"data": "second"}
    cache_with_mock.cache_response(prompt_hash, response2)

    cached = cache_with_mock.get_cached_response(prompt_hash)
    assert cached == response2


# Test: Cache Expiration
def test_cache_expiration(cache_with_mock):
    """Test that cached responses expire after TTL."""
    prompt_hash = "expire_test"
    response = {"data": "will expire"}

    # Cache with 1 second TTL
    cache_with_mock.cache_response(prompt_hash, response, ttl=1)

    # Should be available immediately
    cached = cache_with_mock.get_cached_response(prompt_hash)
    assert cached is not None

    # Wait for expiration
    time.sleep(1.1)

    # Should be expired now
    cached = cache_with_mock.get_cached_response(prompt_hash)
    assert cached is None


def test_cache_with_zero_ttl(cache_with_mock):
    """Test that TTL=0 results in immediate expiration."""
    prompt_hash = "zero_ttl"
    response = {"data": "instant expire"}

    cache_with_mock.cache_response(prompt_hash, response, ttl=0)

    # Should already be expired
    cached = cache_with_mock.get_cached_response(prompt_hash)
    assert cached is None


# Test: Queue Operations
def test_queue_operations(cache_with_mock):
    """Test request queuing and dequeuing (FIFO)."""
    request1 = {"task_id": "task1", "prompt": "First request"}
    request2 = {"task_id": "task2", "prompt": "Second request"}
    request3 = {"task_id": "task3", "prompt": "Third request"}

    # Queue requests
    assert cache_with_mock.queue_request(request1) is True
    assert cache_with_mock.queue_request(request2) is True
    assert cache_with_mock.queue_request(request3) is True

    # Check queue length
    assert cache_with_mock.get_queue_length() == 3

    # Dequeue in FIFO order
    dequeued1 = cache_with_mock.dequeue_request()
    assert dequeued1 == request1

    dequeued2 = cache_with_mock.dequeue_request()
    assert dequeued2 == request2

    assert cache_with_mock.get_queue_length() == 1

    dequeued3 = cache_with_mock.dequeue_request()
    assert dequeued3 == request3

    # Queue should be empty now
    assert cache_with_mock.get_queue_length() == 0
    assert cache_with_mock.dequeue_request() is None


def test_dequeue_empty_queue(cache_with_mock):
    """Test dequeuing from empty queue returns None."""
    result = cache_with_mock.dequeue_request()
    assert result is None


# Test: Connection Error Handling
def test_cache_when_disconnected(cache_disconnected):
    """Test that cache operations fail gracefully when disconnected."""
    # Cache should indicate it's not connected
    assert cache_disconnected.is_connected() is False

    # Operations should return False/None but not raise exceptions
    assert cache_disconnected.cache_response("test", {"data": "test"}) is False
    assert cache_disconnected.get_cached_response("test") is None
    assert cache_disconnected.queue_request({"task": "test"}) is False
    assert cache_disconnected.dequeue_request() is None
    assert cache_disconnected.get_queue_length() == 0


def test_redis_error_handling(cache_with_mock):
    """Test handling of Redis errors during operations."""
    # Simulate Redis error on setex
    cache_with_mock.client.setex = Mock(side_effect=RedisError("Simulated error"))

    result = cache_with_mock.cache_response("test", {"data": "test"})
    assert result is False

    # Simulate Redis error on get
    cache_with_mock.client.get = Mock(side_effect=RedisError("Simulated error"))

    result = cache_with_mock.get_cached_response("test")
    assert result is None


def test_json_encoding_error(cache_with_mock):
    """Test handling of JSON encoding errors."""

    # Create an object that can't be JSON serialized
    class NonSerializable:
        pass

    result = cache_with_mock.cache_response("test", {"obj": NonSerializable()})
    assert result is False


def test_json_decoding_error(cache_with_mock):
    """Test handling of corrupted cache data."""
    # Simulate corrupted data in cache
    cache_with_mock.client.get = Mock(return_value="invalid json {{{")

    result = cache_with_mock.get_cached_response("test")
    assert result is None


# Test: Additional Operations
def test_clear_cache(cache_with_mock):
    """Test clearing all cached responses."""
    # Add multiple cached responses
    cache_with_mock.cache_response("key1", {"data": "1"})
    cache_with_mock.cache_response("key2", {"data": "2"})
    cache_with_mock.cache_response("key3", {"data": "3"})

    # Clear cache
    success = cache_with_mock.clear_cache()
    assert success is True

    # All should be gone
    assert cache_with_mock.get_cached_response("key1") is None
    assert cache_with_mock.get_cached_response("key2") is None
    assert cache_with_mock.get_cached_response("key3") is None


def test_clear_queue(cache_with_mock):
    """Test clearing all queued requests."""
    # Add multiple requests
    cache_with_mock.queue_request({"task": "1"})
    cache_with_mock.queue_request({"task": "2"})
    cache_with_mock.queue_request({"task": "3"})

    assert cache_with_mock.get_queue_length() == 3

    # Clear queue
    success = cache_with_mock.clear_queue()
    assert success is True

    # Queue should be empty
    assert cache_with_mock.get_queue_length() == 0
    assert cache_with_mock.dequeue_request() is None


def test_connection_check(cache_with_mock):
    """Test connection status checking."""
    # Should be connected with mock
    assert cache_with_mock.is_connected() is True

    # Simulate connection loss
    cache_with_mock.client.ping = Mock(side_effect=RedisConnectionError("Lost connection"))

    # Should detect disconnection
    assert cache_with_mock.is_connected() is False


def test_close_connection(cache_with_mock):
    """Test closing Redis connection."""
    cache_with_mock.close()

    # Should be disconnected after close
    assert cache_with_mock._connected is False


# Integration-style test
def test_cache_queue_integration(cache_with_mock):
    """Test combined cache and queue operations."""
    # Cache some responses
    cache_with_mock.cache_response("prompt1", {"result": "cached1"})
    cache_with_mock.cache_response("prompt2", {"result": "cached2"})

    # Queue some requests
    cache_with_mock.queue_request({"task_id": "t1"})
    cache_with_mock.queue_request({"task_id": "t2"})

    # Both systems should work independently
    assert cache_with_mock.get_cached_response("prompt1")["result"] == "cached1"
    assert cache_with_mock.dequeue_request()["task_id"] == "t1"

    assert cache_with_mock.get_cached_response("prompt2")["result"] == "cached2"
    assert cache_with_mock.dequeue_request()["task_id"] == "t2"
