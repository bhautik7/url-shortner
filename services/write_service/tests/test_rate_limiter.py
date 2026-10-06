"""
Unit Tests for Redis-backed Rate Limiter.
"""

from unittest.mock import AsyncMock, MagicMock
import fakeredis.aioredis
import pytest
from starlette.requests import Request
from services.write_service.app.core.rate_limiter import RateLimiter
from shared.utilities.errors import RateLimitError


def create_mock_request(client_ip: str = "192.168.1.100") -> Request:
    """Helper to create a mock Starlette Request with client IP headers."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/urls",
        "headers": [(b"x-real-ip", client_ip.encode())],
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_rate_limiter_within_limit():
    """Test that requests within the allowed quota pass without error."""
    fake_redis = fakeredis.aioredis.FakeRedis()
    try:
        limiter = RateLimiter(redis_client=fake_redis, limit_per_minute=10, enabled=True)
        req = create_mock_request()

        for _ in range(5):
            await limiter.check_rate_limit(req)
    finally:
        await fake_redis.aclose()


@pytest.mark.asyncio
async def test_rate_limiter_exceeded_raises_error():
    """Test that exceeding rate limit quota raises RateLimitError."""
    fake_redis = fakeredis.aioredis.FakeRedis()
    try:
        limiter = RateLimiter(redis_client=fake_redis, limit_per_minute=3, enabled=True)
        req = create_mock_request()

        # Send 3 allowed requests
        for _ in range(3):
            await limiter.check_rate_limit(req)

        # 4th request must exceed quota
        with pytest.raises(RateLimitError) as exc_info:
            await limiter.check_rate_limit(req)

        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "RATE_LIMIT_EXCEEDED"
    finally:
        await fake_redis.aclose()


@pytest.mark.asyncio
async def test_rate_limiter_redis_failure_fails_open():
    """Test that transient Redis failure fails open and does not block client requests."""
    broken_redis = MagicMock()
    broken_redis.pipeline.side_effect = Exception("Redis network timeout")

    limiter = RateLimiter(redis_client=broken_redis, limit_per_minute=10, enabled=True)
    req = create_mock_request()

    # Should fail open without raising an error
    await limiter.check_rate_limit(req)
