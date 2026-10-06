"""
Redirect Business Logic Service for Read Service.

Coordinates Cache-Aside lookup, PostgreSQL fallback, expiration checks,
and cache population.
"""

from datetime import datetime, timezone
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from services.read_service.app.repositories.url_repository import UrlReadRepository
from services.read_service.app.services.cache_service import CacheService
from shared.database.base import get_utc_now
from shared.utilities.errors import ExpiredError, NotFoundError

logger = logging.getLogger("read_service")


class RedirectService:
    """
    Orchestrates the read path and cache-aside redirect flow.
    """

    def __init__(self, repository: UrlReadRepository, cache_service: CacheService):
        self.repository = repository
        self.cache = cache_service

    async def get_destination_url(
        self,
        session: AsyncSession,
        short_code: str,
    ) -> str:
        """
        Resolves short code to its destination long URL following the Cache-Aside pattern.

        Step 1: Check Redis cache first.
        Step 2: If cache HIT:
                - Verify expiration timestamp.
                - If expired, raise HTTP 410.
                - Else return destination long URL immediately.
        Step 3: If cache MISS (or Redis offline):
                - Query PostgreSQL using indexed short_code.
                - If not found, raise HTTP 404.
                - If expired, raise HTTP 410.
                - Populate Redis cache asynchronously with computed TTL.
                - Return destination long URL.
        """
        # --- Step 1: Redis Cache Lookup ---
        cached = await self.cache.get_url(short_code)
        if cached:
            # Check expiration if present in cached payload
            if cached.get("expires_at"):
                try:
                    expires_dt = datetime.fromisoformat(cached["expires_at"])
                    now = get_utc_now()
                    if expires_dt.tzinfo is None:
                        now_cmp = now.replace(tzinfo=None)
                    else:
                        now_cmp = now
                    if now_cmp >= expires_dt:
                        logger.info(
                            f"Cached short code '{short_code}' has expired",
                            extra={"short_code": short_code, "expired_at": cached["expires_at"]},
                        )
                        raise ExpiredError("The requested short URL has expired.")
                except ValueError:
                    # In case of malformed timestamp string, proceed with long_url
                    pass

            logger.debug(
                f"Cache HIT for '{short_code}' -> {cached['long_url']}",
                extra={"short_code": short_code, "cache_hit": True},
            )
            return cached["long_url"]

        # --- Step 2: PostgreSQL Lookup on Cache MISS ---
        logger.debug(
            f"Cache MISS for '{short_code}', querying PostgreSQL",
            extra={"short_code": short_code, "cache_hit": False},
        )
        url_record = await self.repository.get_by_short_code(session, short_code)

        if url_record is None:
            logger.info(
                f"URL not found in PostgreSQL for short code '{short_code}'",
                extra={"short_code": short_code},
            )
            raise NotFoundError(f"Short URL '{short_code}' not found.")

        # Check expiration from database model
        if url_record.is_expired():
            logger.info(
                f"URL record for '{short_code}' is expired in PostgreSQL",
                extra={"short_code": short_code, "expires_at": str(url_record.expires_at)},
            )
            raise ExpiredError("The requested short URL has expired.")

        # --- Step 3: Populate Redis Cache ---
        await self.cache.set_url(
            short_code=url_record.short_code,
            long_url=url_record.long_url,
            expires_at=url_record.expires_at,
        )

        return url_record.long_url
