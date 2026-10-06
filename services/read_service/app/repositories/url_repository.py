"""
URL Database Repository for Read Service.

Encapsulates all PostgreSQL read operations for URLs.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.models.url import URL


class UrlReadRepository:
    """
    Data access layer for querying URLs in PostgreSQL.
    """

    async def get_by_short_code(self, session: AsyncSession, short_code: str) -> Optional[URL]:
        """
        Queries a URL record by its unique short code.

        Uses the B-Tree unique index on `urls.short_code` for O(log N) lookup time.
        """
        stmt = select(URL).where(URL.short_code == short_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
