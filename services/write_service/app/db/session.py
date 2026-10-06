"""
Database Session Provider for Write Service.
"""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from services.write_service.app.core.config import settings
from shared.database.session import DatabaseManager

db_manager = DatabaseManager(
    database_url=settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining a database session."""
    async with db_manager.session() as session:
        yield session
