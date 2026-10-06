"""
Unit Tests for Read Service Cache Logic and TTL Calculations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from services.read_service.app.services.cache_service import CacheService
from shared.database.base import get_utc_now


def test_compute_ttl_no_expiration():
    """Test that URLs without expiration receive default TTL (86400s)."""
    service = CacheService(redis_client=None, default_ttl=86400, max_ttl=604800)
    assert service.compute_ttl(expires_at=None) == 86400


def test_compute_ttl_with_shorter_expiration():
    """Test that URLs expiring in 30 minutes receive TTL <= 1800s."""
    now = get_utc_now()
    expires_at = now + timedelta(minutes=30)
    service = CacheService(redis_client=None, default_ttl=86400, max_ttl=604800)

    ttl = service.compute_ttl(expires_at=expires_at, now=now)
    assert ttl == 1800


def test_compute_ttl_with_far_future_expiration_capped():
    """Test that URLs expiring in 30 days are capped at max_ttl (7 days / 604800s)."""
    now = get_utc_now()
    expires_at = now + timedelta(days=30)
    service = CacheService(redis_client=None, default_ttl=86400, max_ttl=604800)

    ttl = service.compute_ttl(expires_at=expires_at, now=now)
    assert ttl == 604800


def test_compute_ttl_already_expired_returns_none():
    """Test that already expired URLs return None (not cached)."""
    now = get_utc_now()
    expires_at = now - timedelta(seconds=10)
    service = CacheService(redis_client=None, default_ttl=86400, max_ttl=604800)

    ttl = service.compute_ttl(expires_at=expires_at, now=now)
    assert ttl is None


@pytest.mark.asyncio
async def test_cache_service_get_and_set():
    """Test normal cache get and set operations with JSON serialization."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"long_url": "https://example.com", "expires_at": null}'

    service = CacheService(redis_client=mock_redis)
    result = await service.get_url("abc123")

    assert result is not None
    assert result["long_url"] == "https://example.com"
    assert result["expires_at"] is None


@pytest.mark.asyncio
async def test_cache_service_redis_failure_resilience():
    """Test that Redis failure during lookup returns None instead of raising an error."""
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection refused")

    service = CacheService(redis_client=mock_redis)
    result = await service.get_url("abc123")

    # Should fall back to None without crashing
    assert result is None
