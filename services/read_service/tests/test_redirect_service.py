"""
Unit Tests for RedirectService Cache-Aside Logic.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
from services.read_service.app.repositories.url_repository import UrlReadRepository
from services.read_service.app.services.cache_service import CacheService
from services.read_service.app.services.redirect_service import RedirectService
from shared.database.base import get_utc_now
from shared.models.url import URL
from shared.utilities.errors import ExpiredError, NotFoundError


@pytest.mark.asyncio
async def test_redirect_service_cache_hit():
    """Test that a cache HIT returns the destination URL without querying PostgreSQL."""
    mock_repo = AsyncMock(spec=UrlReadRepository)
    mock_cache = AsyncMock(spec=CacheService)
    mock_cache.get_url.return_value = {
        "long_url": "https://example.com/cached",
        "expires_at": None,
    }

    mock_session = AsyncMock()
    service = RedirectService(repository=mock_repo, cache_service=mock_cache)

    destination = await service.get_destination_url(mock_session, "hit123")

    assert destination == "https://example.com/cached"
    # PostgreSQL repo should NOT have been called
    mock_repo.get_by_short_code.assert_not_called()


@pytest.mark.asyncio
async def test_redirect_service_cache_miss_db_hit():
    """Test that a cache MISS queries PostgreSQL and populates Redis."""
    mock_repo = AsyncMock(spec=UrlReadRepository)
    mock_cache = AsyncMock(spec=CacheService)
    mock_cache.get_url.return_value = None  # Cache miss

    db_url = URL(
        id=1,
        short_code="miss123",
        long_url="https://example.com/from-db",
        expires_at=None,
    )
    mock_repo.get_by_short_code.return_value = db_url

    mock_session = AsyncMock()
    service = RedirectService(repository=mock_repo, cache_service=mock_cache)

    destination = await service.get_destination_url(mock_session, "miss123")

    assert destination == "https://example.com/from-db"
    # DB repo should have been queried
    mock_repo.get_by_short_code.assert_called_once_with(mock_session, "miss123")
    # Redis cache should be populated
    mock_cache.set_url.assert_called_once_with(
        short_code="miss123",
        long_url="https://example.com/from-db",
        expires_at=None,
    )


@pytest.mark.asyncio
async def test_redirect_service_not_found_raises_404():
    """Test that non-existent short code raises NotFoundError (404)."""
    mock_repo = AsyncMock(spec=UrlReadRepository)
    mock_cache = AsyncMock(spec=CacheService)
    mock_cache.get_url.return_value = None
    mock_repo.get_by_short_code.return_value = None

    mock_session = AsyncMock()
    service = RedirectService(repository=mock_repo, cache_service=mock_cache)

    with pytest.raises(NotFoundError):
        await service.get_destination_url(mock_session, "not-found")


@pytest.mark.asyncio
async def test_redirect_service_expired_url_raises_410():
    """Test that an expired URL in PostgreSQL raises ExpiredError (410)."""
    mock_repo = AsyncMock(spec=UrlReadRepository)
    mock_cache = AsyncMock(spec=CacheService)
    mock_cache.get_url.return_value = None

    db_url = URL(
        id=2,
        short_code="expired1",
        long_url="https://example.com/expired",
        expires_at=get_utc_now() - timedelta(minutes=10),
    )
    mock_repo.get_by_short_code.return_value = db_url

    mock_session = AsyncMock()
    service = RedirectService(repository=mock_repo, cache_service=mock_cache)

    with pytest.raises(ExpiredError):
        await service.get_destination_url(mock_session, "expired1")
