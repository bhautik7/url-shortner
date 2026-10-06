"""
End-to-End Integration Tests for Write Service and Read Service.

Covers:
1. Create short URL
2. Redirect (HTTP 302)
3. Redis cache hit
4. Redis cache miss
5. Custom alias creation
6. Duplicate alias conflict (HTTP 409)
7. Expired URL (HTTP 410)
8. Invalid URL validation (HTTP 400)
9. Counter batch allocation across instances
"""

from datetime import timedelta
import pytest
from httpx import AsyncClient
from shared.database.base import get_utc_now


@pytest.mark.asyncio
async def test_create_short_url_and_redirect_flow(write_client: AsyncClient, read_client: AsyncClient, fake_redis):
    """
    Test standard URL creation and redirection flow.
    1. POST /api/v1/urls -> 201 Created
    2. GET /{short_code} -> 302 Found redirect
    3. Verify Redis cache population
    """
    target_url = "https://example.com/system-design/interview-prep"
    payload = {
        "long_url": target_url,
        "custom_alias": None,
        "expiration_date": None,
    }

    # 1. Create short URL
    response = await write_client.post("/api/v1/urls", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert "short_code" in data
    assert data["long_url"] == target_url
    assert data["short_url"] == f"http://localhost/{data['short_code']}"

    short_code = data["short_code"]

    # 2. First redirect (Cache Miss -> DB -> Redis populated)
    redirect_resp = await read_client.get(f"/{short_code}")
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers["location"] == target_url

    # 3. Verify key is now present in Redis cache
    cached_bytes = await fake_redis.get(f"url:{short_code}")
    assert cached_bytes is not None

    # 4. Second redirect (Cache Hit directly from Redis)
    cached_redirect_resp = await read_client.get(f"/{short_code}")
    assert cached_redirect_resp.status_code == 302
    assert cached_redirect_resp.headers["location"] == target_url


@pytest.mark.asyncio
async def test_custom_alias_creation_and_conflict(write_client: AsyncClient, read_client: AsyncClient):
    """
    Test custom alias creation and duplicate conflict handling.
    1. Create URL with custom alias 'my-awesome-link' -> 201 Created
    2. Attempt to create another URL with identical alias -> 409 Conflict
    3. GET /my-awesome-link -> 302 Found
    """
    alias = "my-awesome-link"
    payload = {
        "long_url": "https://example.com/custom-page",
        "custom_alias": alias,
        "expiration_date": None,
    }

    # 1. Create with custom alias
    resp1 = await write_client.post("/api/v1/urls", json=payload)
    assert resp1.status_code == 201
    data = resp1.json()
    assert data["short_code"] == alias

    # 2. Attempt duplicate creation
    resp2 = await write_client.post("/api/v1/urls", json=payload)
    assert resp2.status_code == 409
    err_body = resp2.json()
    assert err_body["error"]["code"] == "ALIAS_ALREADY_EXISTS"

    # 3. Test redirection
    redirect_resp = await read_client.get(f"/{alias}")
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers["location"] == "https://example.com/custom-page"


@pytest.mark.asyncio
async def test_expired_url_returns_410(write_client: AsyncClient, read_client: AsyncClient, db_session_factory):
    """
    Test that an expired URL returns HTTP 410 Gone and does not redirect.
    """
    from shared.models.url import URL

    # Seed an already expired URL directly in database
    past_expiration = get_utc_now() - timedelta(minutes=15)
    async with db_session_factory() as session:
        url_record = URL(
            short_code="expired-deal",
            long_url="https://example.com/expired-deal",
            expires_at=past_expiration,
            created_by="test",
        )
        session.add(url_record)
        await session.commit()

    # Attempt to redirect to expired link
    resp = await read_client.get("/expired-deal")
    assert resp.status_code == 410
    body = resp.json()
    assert body["error"]["code"] == "URL_EXPIRED"


@pytest.mark.asyncio
async def test_non_existent_url_returns_404(read_client: AsyncClient):
    """
    Test that requesting a non-existent short code returns HTTP 404 Not Found.
    """
    resp = await read_client.get("/non-existent-code")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "URL_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_url_payload_returns_400(write_client: AsyncClient):
    """
    Test that invalid request inputs return HTTP 400 Bad Request with standardized error.
    """
    # 1. Invalid URL scheme
    resp1 = await write_client.post("/api/v1/urls", json={"long_url": "ftp://invalid-scheme.com"})
    assert resp1.status_code == 400
    assert resp1.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Invalid alias format (contains forbidden characters)
    resp2 = await write_client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com", "custom_alias": "invalid alias spaces!"},
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Invalid expiration date in the past
    past_date_iso = (get_utc_now() - timedelta(days=1)).isoformat()
    resp3 = await write_client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com", "expiration_date": past_date_iso},
    )
    assert resp3.status_code == 400
    assert resp3.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_counter_batching_multiple_creations(write_client: AsyncClient):
    """
    Test sequential URL creations utilizing counter batching.
    """
    short_codes = set()
    for i in range(15):
        payload = {"long_url": f"https://example.com/page-{i}"}
        resp = await write_client.post("/api/v1/urls", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        short_codes.add(data["short_code"])

    # All 15 generated short codes must be strictly distinct
    assert len(short_codes) == 15
