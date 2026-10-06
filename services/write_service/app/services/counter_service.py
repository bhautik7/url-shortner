"""
Centralized Counter and In-Memory Batch Range Allocator.

Architecture:
To achieve high throughput and avoid Redis network round-trips for every single write,
each Write Service instance leases a block of IDs in advance using Redis INCRBY.

Example:
- Instance A leases [1000001, 1001000] (batch size 1000)
- Instance B leases [1001001, 1002000]
- Each instance dispenses IDs locally from its in-memory pool using an async lock.
- When an instance exhausts its range, it atomically requests the next batch from Redis.

Failure & Discard Policy:
If a Write Service instance restarts or crashes before consuming all leased IDs in its batch,
those unused numbers are simply skipped (e.g. gap in integer sequence).
This is completely acceptable in URL shorteners because Base62 space (62^6 ≈ 56.8B) is massive,
and skipping gaps has zero impact on correctness or uniqueness.
"""

import asyncio
import logging
from typing import Optional
import redis.asyncio as redis
from shared.utilities.errors import DependencyUnavailableError

logger = logging.getLogger("write_service")


class CounterService:
    """
    Thread-safe & async-safe Counter Service with Redis batch leasing.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        counter_key: str = "url_shortener:global_counter",
        batch_size: int = 1000,
        start_offset: int = 1000000,
    ):
        self.redis = redis_client
        self.counter_key = counter_key
        self.batch_size = batch_size
        self.start_offset = start_offset

        # In-memory range tracking
        self._current_id: int = 0
        self._max_id: int = 0
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_counter_initialized(self) -> None:
        """
        Ensures the Redis global counter has an initial value >= start_offset.
        Uses SETNX to avoid overwriting existing counter state in production.
        """
        if self._initialized:
            return
        try:
            # We use SETNX so if the key does not exist, we initialize it to start_offset
            await self.redis.set(self.counter_key, self.start_offset, nx=True)
            self._initialized = True
        except Exception as exc:
            logger.error(f"Failed to initialize Redis counter key: {exc}")
            raise DependencyUnavailableError(
                "Failed to initialize Redis counter. Counter service unavailable."
            ) from exc

    async def _fetch_next_batch(self) -> None:
        """
        Atomically requests the next ID range from Redis using INCRBY.

        We intentionally allocate counter ranges in batches so each
        Write Service instance does not need a Redis round-trip for
        every URL creation.
        """
        await self._ensure_counter_initialized()
        try:
            # INCRBY atomically increments the counter by batch_size and returns the new high-water mark
            new_max = await self.redis.incrby(self.counter_key, self.batch_size)
            self._max_id = new_max
            self._current_id = new_max - self.batch_size + 1
            logger.info(
                f"Leased new counter batch: [{self._current_id}, {self._max_id}] (size={self.batch_size})",
                extra={"batch_start": self._current_id, "batch_end": self._max_id},
            )
        except Exception as exc:
            logger.error(f"Failed to lease counter batch from Redis: {exc}", exc_info=True)
            raise DependencyUnavailableError(
                "Redis counter service is temporarily unavailable. Cannot allocate URL ID."
            ) from exc

    async def get_next_id(self) -> int:
        """
        Retrieves the next unique monotonic integer ID for short code generation.
        Dispenses from local memory under an async lock, leasing a new batch when exhausted.

        Returns:
            Unique positive integer ID.
        """
        async with self._lock:
            if self._current_id > self._max_id or self._max_id == 0:
                await self._fetch_next_batch()

            allocated_id = self._current_id
            self._current_id += 1
            return allocated_id
