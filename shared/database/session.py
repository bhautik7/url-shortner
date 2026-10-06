"""
Database Session and Engine Management.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    database_url: str,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    echo: bool = False,
) -> AsyncEngine:
    """
    Creates an asynchronous SQLAlchemy engine.
    """
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,  # Proactively test connection liveness before using
        echo=echo,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Creates an async session factory bound to the provided engine.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


class DatabaseManager:
    """
    Encapsulates engine and session factory lifecycle.
    """

    def __init__(self, database_url: str, pool_size: int = 20, max_overflow: int = 10):
        self.database_url = database_url
        self.engine: AsyncEngine = create_engine(
            database_url=database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)

    async def close(self) -> None:
        """Disposes the database connection pool."""
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for obtaining an async session."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency generator for FastAPI routes."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """Health/readiness check to verify database connectivity."""
        try:
            async with self.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar_one_or_none() == 1
        except Exception:
            return False
