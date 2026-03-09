"""
Redis Cache and Queue Manager for Claude Code API Service.

Provides:
- Response caching with TTL
- Request queuing for task management
- Graceful connection error handling
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Redis-backed cache and queue manager.

    Features:
    - Response caching with configurable TTL
    - Request queue management
    - Graceful error handling
    - Connection retry logic
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        decode_responses: bool = True,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        """
        Initialize Redis connection.

        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            password: Optional password for authentication
            decode_responses: Whether to decode byte responses to strings
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
            )

            # Test connection
            self.client.ping()
            logger.info(f"Successfully connected to Redis at {host}:{port}")
            self._connected = True

        except (RedisConnectionError, RedisError) as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.warning("Cache and queue operations will be disabled")
            self.client = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        if not self._connected or not self.client:
            return False

        try:
            self.client.ping()
            return True
        except (RedisConnectionError, RedisError):
            self._connected = False
            return False

    def cache_response(self, prompt_hash: str, response: dict[str, Any], ttl: int = 3600) -> bool:
        """
        Cache a response with TTL.

        Args:
            prompt_hash: Hash of the prompt (used as cache key)
            response: Response data to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)

        Returns:
            True if cached successfully, False otherwise
        """
        if not self.is_connected():
            logger.debug("Cache unavailable, skipping cache_response")
            return False

        try:
            cache_key = f"cache:response:{prompt_hash}"
            serialized = json.dumps(response)

            # Set with expiration
            self.client.setex(cache_key, ttl, serialized)
            logger.debug(f"Cached response for {prompt_hash} with TTL={ttl}s")
            return True

        except (RedisError, TypeError) as e:
            logger.error(f"Failed to cache response: {e}")
            return False

    def get_cached_response(self, prompt_hash: str) -> dict[str, Any] | None:
        """
        Retrieve a cached response.

        Args:
            prompt_hash: Hash of the prompt (cache key)

        Returns:
            Cached response data if found and valid, None otherwise
        """
        if not self.is_connected():
            logger.debug("Cache unavailable, skipping get_cached_response")
            return None

        try:
            cache_key = f"cache:response:{prompt_hash}"
            cached = self.client.get(cache_key)

            if cached is None:
                logger.debug(f"Cache miss for {prompt_hash}")
                return None

            response = json.loads(cached)
            logger.debug(f"Cache hit for {prompt_hash}")
            return response

        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Failed to retrieve cached response: {e}")
            return None

    def queue_request(self, request_data: dict[str, Any]) -> bool:
        """
        Add a request to the queue.

        Args:
            request_data: Request data to queue (will be JSON serialized)

        Returns:
            True if queued successfully, False otherwise
        """
        if not self.is_connected():
            logger.debug("Queue unavailable, skipping queue_request")
            return False

        try:
            queue_key = "queue:requests"
            serialized = json.dumps(request_data)

            # Push to right end of list (FIFO)
            self.client.rpush(queue_key, serialized)
            logger.debug(f"Queued request: {request_data.get('task_id', 'unknown')}")
            return True

        except (RedisError, TypeError) as e:
            logger.error(f"Failed to queue request: {e}")
            return False

    def dequeue_request(self) -> dict[str, Any] | None:
        """
        Remove and return the next request from the queue.

        Returns:
            Request data if queue is not empty, None otherwise
        """
        if not self.is_connected():
            logger.debug("Queue unavailable, skipping dequeue_request")
            return None

        try:
            queue_key = "queue:requests"

            # Pop from left end of list (FIFO)
            serialized = self.client.lpop(queue_key)

            if serialized is None:
                logger.debug("Queue is empty")
                return None

            request_data = json.loads(serialized)
            logger.debug(f"Dequeued request: {request_data.get('task_id', 'unknown')}")
            return request_data

        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Failed to dequeue request: {e}")
            return None

    def get_queue_length(self) -> int:
        """
        Get the current queue length.

        Returns:
            Number of items in the queue, or 0 if unavailable
        """
        if not self.is_connected():
            return 0

        try:
            queue_key = "queue:requests"
            length = self.client.llen(queue_key)
            return length
        except RedisError as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    def clear_cache(self) -> bool:
        """
        Clear all cached responses.

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            # Find all cache keys
            keys = self.client.keys("cache:response:*")
            if keys:
                self.client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cached responses")
            return True
        except RedisError as e:
            logger.error(f"Failed to clear cache: {e}")
            return False

    def clear_queue(self) -> bool:
        """
        Clear all queued requests.

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            queue_key = "queue:requests"
            self.client.delete(queue_key)
            logger.info("Cleared request queue")
            return True
        except RedisError as e:
            logger.error(f"Failed to clear queue: {e}")
            return False

    def close(self):
        """Close the Redis connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("Closed Redis connection")
            except RedisError as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self._connected = False
