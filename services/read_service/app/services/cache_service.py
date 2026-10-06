"""
Redis Cache-Aside Service for Read Service.

Handles:
- Cache lookups
- Cache population with intelligent TTL computation
- Graceful degradation during Redis downtime
"""

from datetime import datetime, timezone
import json
import logging
from typing import Optional, TypedDict
import redis.asyncio as redis
from shared.database.base import get_utc_now

logger = logging.getLogger("read_service")


class CachedUrlData(TypedDict):
    long_url: str
    expires_at: Optional[str]


class CacheService:
    """
    Manages Redis caching for shortened URLs using the cache-aside pattern.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis],
        key_prefix: str = "url:",
        default_ttl: int = 86400,
        max_ttl: int = 604800,
    ):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.max_ttl = max_ttl

    def _make_key(self, short_code: str) -> str:
        """Constructs the Redis key for a short code."""
        return f"{self.key_prefix}{short_code}"

    def compute_ttl(
        self,
        expires_at: Optional[datetime],
        now: Optional[datetime] = None,
    ) -> Optional[int]:
        """
        Calculates the appropriate TTL in seconds for Redis caching.

        Rules:
        1. If URL never expires (`expires_at is None`), use default TTL (e.g. 24 hours).
        2. If URL has an expiration date:
           - Calculate seconds remaining until expiration.
           - If already expired (remaining <= 0), return None (should not cache).
           - If remaining < default TTL, Redis TTL MUST NOT exceed remaining lifetime.
           - If remaining > max TTL cap, set TTL to max TTL cap (prevents stale infinite keys).
        """
        if expires_at is None:
            return self.default_ttl

        current_time = now or get_utc_now()
        if expires_at.tzinfo is None:
            cmp_now = current_time.replace(tzinfo=None)
        else:
            cmp_now = current_time

        remaining_seconds = int((expires_at - cmp_now).total_seconds())
        if remaining_seconds <= 0:
            # Already expired, do not cache
            return None

        # Intelligently cap TTL so it never outlives the URL's actual expiration
        ttl = min(remaining_seconds, self.max_ttl)
        return max(1, ttl)

    async def get_url(self, short_code: str) -> Optional[CachedUrlData]:
        """
        Retrieves cached URL data from Redis.

        Resilience:
        If Redis is unreachable or throws a connection error, logs a warning
        and returns None, seamlessly falling back to PostgreSQL.
        """
        if self.redis is None:
            return None

        key = self._make_key(short_code)
        try:
            raw_val = await self.redis.get(key)
            if raw_val is None:
                return None

            if isinstance(raw_val, bytes):
                raw_val = raw_val.decode("utf-8")

            data = json.loads(raw_val)
            return {
                "long_url": data["long_url"],
                "expires_at": data.get("expires_at"),
            }
        except Exception as exc:
            logger.warning(
                f"Redis cache lookup failed for '{short_code}': {exc}. Falling back to DB.",
                extra={"short_code": short_code, "error": str(exc)},
            )
            return None

    async def set_url(
        self,
        short_code: str,
        long_url: str,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """
        Populates the Redis cache for a short code with an intelligent TTL.

        Resilience:
        If Redis is unreachable, catches the exception and logs a warning.
        Does not propagate error to the caller, ensuring redirection succeeds.
        """
        if self.redis is None:
            return

        ttl = self.compute_ttl(expires_at)
        if ttl is None:
            # URL is expired or invalid for caching
            return

        key = self._make_key(short_code)
        payload = {
            "long_url": long_url,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        try:
            json_data = json.dumps(payload)
            await self.redis.set(key, json_data, ex=ttl)
            logger.debug(
                f"Populated cache for '{short_code}' with TTL={ttl}s",
                extra={"short_code": short_code, "ttl": ttl},
            )
        except Exception as exc:
            logger.warning(
                f"Failed to populate Redis cache for '{short_code}': {exc}",
                extra={"short_code": short_code, "error": str(exc)},
            )
