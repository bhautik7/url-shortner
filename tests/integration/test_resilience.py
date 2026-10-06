"""
Resilience & Fault-Tolerance Integration Tests.

Tests:
1. Redis unavailable during read -> gracefully falls back to PostgreSQL and succeeds (302).
2. Redis unavailable during write -> returns HTTP 503 Dependency Unavailable.
3. Health and readiness endpoints.
"""

from unittest.mock import AsyncMock
import pytest
from httpx import AsyncClient
from shared.models.url import URL


@pytest.mark.asyncio
async def test_redis_unavailable_during_read_falls_back_to_db(read_app, db_session_factory):
    """
    Resilience Test:
    When Redis cache is completely unreachable during a redirect request,
    the Read Service MUST NOT crash or fail the request.
    It must fall back seamlessly to PostgreSQL and return HTTP 302 Found.
    """
    from httpx import ASGITransport, AsyncClient

    # 1. Seed URL in database
    async with db_session_factory() as session:
        url_record = URL(
            short_code="resilience-test",
            long_url="https://example.com/resilient-fallback",
            expires_at=None,
            created_by="resilience_test",
        )
        session.add(url_record)
        await session.commit()

    # 2. Simulate complete Redis failure by attaching an error-throwing client
    broken_redis = AsyncMock()
    broken_redis.get.side_effect = Exception("Redis connection refused / timed out")
    broken_redis.set.side_effect = Exception("Redis connection refused / timed out")
    read_app.state.cache_service.redis = broken_redis

    transport = ASGITransport(app=read_app)
    async with AsyncClient(transport=transport, base_url="http://localhost", follow_redirects=False) as client:
        resp = await client.get("/resilience-test")
        # Must still succeed with 302 redirect!
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.com/resilient-fallback"


@pytest.mark.asyncio
async def test_redis_unavailable_during_write_returns_503(write_app):
    """
    Resilience Test:
    When Redis counter is unreachable during short URL generation,
    Write Service must return HTTP 503 Service Unavailable with clean JSON error.
    """
    from httpx import ASGITransport, AsyncClient

    broken_redis = AsyncMock()
    broken_redis.incrby.side_effect = Exception("Redis connection timeout")
    broken_redis.set.side_effect = Exception("Redis connection timeout")

    # Invalidate counter memory state and inject broken redis
    write_app.state.counter_service.redis = broken_redis
    write_app.state.counter_service._current_id = 0
    write_app.state.counter_service._max_id = 0
    write_app.state.counter_service._initialized = False

    transport = ASGITransport(app=write_app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/api/v1/urls",
            json={"long_url": "https://example.com/fail-case"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_health_and_readiness_probes(write_client: AsyncClient, read_client: AsyncClient):
    """
    Test health (liveness) and readiness probes on both services.
    """
    # Write Service
    w_health = await write_client.get("/health")
    assert w_health.status_code == 200
    assert w_health.json()["status"] == "ok"

    w_ready = await write_client.get("/ready")
    assert w_ready.status_code in (200, 503)

    # Read Service
    r_health = await read_client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ready = await read_client.get("/ready")
    assert r_ready.status_code in (200, 503)
