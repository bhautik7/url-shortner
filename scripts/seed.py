"""
Database and Redis Seeding Script.

Seeds sample short URLs and initializes the Redis counter for local development and testing.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
import redis.asyncio as redis
from shared.config.base import CommonSettings
from shared.database.base import get_utc_now
from shared.database.session import DatabaseManager
from shared.models.url import URL
from shared.utilities.base62 import encode_base62
from shared.utilities.logging import setup_logger

logger = setup_logger("seed_script", log_level="INFO")

SAMPLE_DATA = [
    {
        "short_code": "docs",
        "long_url": "https://fastapi.tiangolo.com/",
        "custom_alias": "docs",
        "expires_at": None,
    },
    {
        "short_code": "github",
        "long_url": "https://github.com",
        "custom_alias": "github",
        "expires_at": None,
    },
    {
        "short_code": "google",
        "long_url": "https://google.com",
        "custom_alias": "google",
        "expires_at": None,
    },
    {
        "short_code": "promo2026",
        "long_url": "https://example.com/promo-sale",
        "custom_alias": "promo2026",
        "expires_at": get_utc_now() + timedelta(days=30),
    },
    {
        "short_code": "expired-link",
        "long_url": "https://example.com/expired-flash-deal",
        "custom_alias": "expired-link",
        "expires_at": get_utc_now() - timedelta(days=1),  # Already expired
    },
]


async def seed() -> None:
    settings = CommonSettings()
    db_manager = DatabaseManager(database_url=settings.DATABASE_URL)
    redis_client = redis.from_url(settings.REDIS_URL)

    try:
        # 1. Initialize Redis Counter if not set
        counter_key = "url_shortener:global_counter"
        current_counter = await redis_client.get(counter_key)
        if current_counter is None:
            await redis_client.set(counter_key, 1000000)
            logger.info("Initialized Redis counter to 1,000,000")
        else:
            logger.info(f"Existing Redis counter found at {int(current_counter)}")

        # 2. Seed URLs into PostgreSQL
        async with db_manager.session() as session:
            for item in SAMPLE_DATA:
                stmt = select(URL).where(URL.short_code == item["short_code"])
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()

                if not existing:
                    url_record = URL(
                        short_code=item["short_code"],
                        long_url=item["long_url"],
                        custom_alias=item["custom_alias"],
                        expires_at=item["expires_at"],
                        created_by="seed_script",
                    )
                    session.add(url_record)
                    logger.info(f"Seeded URL: /{item['short_code']} -> {item['long_url']}")

            # Seed 5 generated Base62 URLs
            base_id = 1000001
            for i in range(5):
                code = encode_base62(base_id + i)
                stmt = select(URL).where(URL.short_code == code)
                res = await session.execute(stmt)
                if not res.scalar_one_or_none():
                    url_record = URL(
                        short_code=code,
                        long_url=f"https://example.org/resource/{i + 1}",
                        custom_alias=None,
                        expires_at=None,
                        created_by="seed_script",
                    )
                    session.add(url_record)
                    logger.info(f"Seeded Base62 URL: /{code} -> {url_record.long_url}")

            await session.commit()
            logger.info("Database seeding completed successfully.")

    finally:
        await redis_client.aclose()
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(seed())
