"""
URL Database Repository for Write Service.

Encapsulates all PostgreSQL interactions and transactions for URLs.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from shared.models.url import URL
from shared.utilities.errors import ConflictError


class UrlWriteRepository:
    """
    Data access layer for writing and querying URLs in PostgreSQL.
    """

    async def get_by_short_code(self, session: AsyncSession, short_code: str) -> Optional[URL]:
        """
        Queries a URL record by its unique short code.
        """
        stmt = select(URL).where(URL.short_code == short_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_custom_alias(self, session: AsyncSession, custom_alias: str) -> Optional[URL]:
        """
        Queries a URL record by its custom alias.
        """
        stmt = select(URL).where(URL.custom_alias == custom_alias)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_url(
        self,
        session: AsyncSession,
        short_code: str,
        long_url: str,
        expires_at: Optional[datetime] = None,
        custom_alias: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> URL:
        """
        Persists a new URL within an active database transaction.

        Transaction Lifecycle:
        - The caller provides an active AsyncSession.
        - `session.add(new_url)` stages the entity in memory.
        - `session.flush()` or `session.commit()` issues INSERT to PostgreSQL.
        - If a duplicate short_code or custom_alias is detected by the DB UNIQUE constraint,
          PostgreSQL raises an IntegrityError.
        - The repository catches IntegrityError, triggers an explicit `session.rollback()`,
          and raises a domain `ConflictError` to return a 409 Conflict.
        """
        url_record = URL(
            short_code=short_code,
            long_url=long_url,
            expires_at=expires_at,
            custom_alias=custom_alias,
            created_by=created_by,
        )

        session.add(url_record)
        try:
            # Flush sends the SQL INSERT immediately to trigger any unique constraint checks
            await session.flush()
            # Commit finalizes the transaction on disk
            await session.commit()
            await session.refresh(url_record)
            return url_record
        except IntegrityError as exc:
            # Explicit rollback releases any held row locks and clears session state
            await session.rollback()
            raise ConflictError(
                message=f"Short code or alias '{short_code}' already exists."
            ) from exc
