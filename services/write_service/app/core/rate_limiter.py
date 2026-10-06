"""
Redis-backed Rate Limiter for URL Creation.

Uses a 1-minute fixed window counter per client IP address.
"""

import logging
import time
from typing import Optional
from fastapi import Request
import redis.asyncio as redis
from shared.utilities.errors import RateLimitError

logger = logging.getLogger("write_service")


class RateLimiter:
    """
    Redis-based rate limiter using atomic increment with expiry.
    """

    def __init__(self, redis_client: redis.Redis, limit_per_minute: int = 100, enabled: bool = True):
        self.redis_client = redis_client
        self.limit_per_minute = limit_per_minute
        self.enabled = enabled

    def _get_client_ip(self, request: Request) -> str:
        """Extracts the client IP from proxy headers or direct connection."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in the list is the original client
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    async def check_rate_limit(self, request: Request) -> None:
        """
        Evaluates whether the client IP has exceeded the allowed request quota.

        Raises:
            RateLimitError: If request count in the current 1-minute window exceeds limit.
        """
        if not self.enabled:
            return

        client_ip = self._get_client_ip(request)
        # 1-minute window bucket based on Unix timestamp // 60
        current_minute = int(time.time() // 60)
        key = f"rate_limit:write:{client_ip}:{current_minute}"

        try:
            # Atomically increment and set TTL (65 seconds to allow safe transition)
            async with self.redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 65)
                results = await pipe.execute()

            current_count = results[0]
            if current_count > self.limit_per_minute:
                logger.warning(
                    f"Rate limit exceeded for IP {client_ip}: {current_count}/{self.limit_per_minute}",
                    extra={"client_ip": client_ip, "count": current_count},
                )
                raise RateLimitError(
                    message=f"Rate limit exceeded. Maximum {self.limit_per_minute} URL creations per minute."
                )
        except RateLimitError:
            raise
        except Exception as e:
            # In case of transient Redis errors during rate check, log warning and allow traffic
            # to preserve write availability (fail-open for rate limiter)
            logger.warning(f"Rate limiting check failed due to Redis error: {e}. Failing open.")
