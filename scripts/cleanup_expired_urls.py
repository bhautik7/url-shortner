"""
Background Cleanup Script for Expired URLs.

Deletes expired URL records from PostgreSQL in batches to prevent
prolonged table lock contention on high-volume production databases.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from sqlalchemy import delete, select
import redis.asyncio as redis
from shared.config.base import CommonSettings
from shared.database.base import get_utc_now
from shared.database.session import DatabaseManager
from shared.models.url import URL
from shared.utilities.logging import setup_logger

logger = setup_logger("cleanup_worker", log_level="INFO")


async def cleanup_expired_urls(batch_size: int = 500) -> int:
    """
    Finds and deletes URLs where expires_at <= NOW().

    Args:
        batch_size: Number of records to delete per transaction cycle.

    Returns:
        Total number of deleted expired records.
    """
    settings = CommonSettings()
    db_manager = DatabaseManager(
        database_url=settings.DATABASE_URL,
        pool_size=5,
        max_overflow=2,
    )

    total_deleted = 0
    now = get_utc_now()
    logger.info(f"Starting expired URL cleanup job at {now.isoformat()}...")

    # Connect to Redis to purge any cached keys as well
    redis_client = None
    try:
        redis_client = redis.from_url(settings.REDIS_URL, socket_timeout=2.0)
    except Exception as e:
        logger.warning(f"Could not connect to Redis during cleanup: {e}")

    try:
        while True:
            async with db_manager.session() as session:
                # Query IDs and short_codes of next batch of expired URLs
                stmt = (
                    select(URL.id, URL.short_code)
                    .where(URL.expires_at.is_not(None))
                    .where(URL.expires_at <= now)
                    .limit(batch_size)
                )
                result = await session.execute(stmt)
                expired_records = result.all()

                if not expired_records:
                    break

                ids_to_delete = [row[0] for row in expired_records]
                short_codes_to_evict = [row[1] for row in expired_records]

                # Delete from PostgreSQL
                del_stmt = delete(URL).where(URL.id.in_(ids_to_delete))
                await session.execute(del_stmt)
                await session.commit()

                # Invalidate from Redis cache
                if redis_client:
                    try:
                        cache_keys = [f"url:{code}" for code in short_codes_to_evict]
                        if cache_keys:
                            await redis_client.delete(*cache_keys)
                    except Exception as redis_err:
                        logger.warning(f"Failed to evict expired keys from Redis: {redis_err}")

                batch_count = len(ids_to_delete)
                total_deleted += batch_count
                logger.info(f"Purged batch of {batch_count} expired URLs from database.")

    finally:
        if redis_client:
            await redis_client.aclose()
        await db_manager.close()

    logger.info(f"Cleanup finished. Total expired URLs deleted: {total_deleted}")
    return total_deleted


if __name__ == "__main__":
    count = asyncio.run(cleanup_expired_urls())
    sys.exit(0)
