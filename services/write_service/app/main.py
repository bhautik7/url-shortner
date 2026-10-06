"""
Main Entry Point for Write Service Application.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis
from services.write_service.app.api.health import router as health_router
from services.write_service.app.api.routes import router as url_router
from services.write_service.app.core.config import settings
from services.write_service.app.core.rate_limiter import RateLimiter
from services.write_service.app.db.session import db_manager
from services.write_service.app.repositories.url_repository import UrlWriteRepository
from services.write_service.app.services.counter_service import CounterService
from services.write_service.app.services.url_service import UrlWriteService
from shared.utilities.errors import register_exception_handlers
from shared.utilities.logging import StructuredLoggingMiddleware, setup_logger

logger = setup_logger(service_name=settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)

# Global redis client reference for readiness probe
redis_client: redis.Redis = None  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application Lifespan Context Manager.
    Handles startup and shutdown resource lifecycles.
    """
    global redis_client
    logger.info("Initializing Write Service dependencies...")

    # Initialize async Redis client connection pool
    redis_client = redis.from_url(
        settings.REDIS_URL,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
        decode_responses=False,
    )

    # Instantiate repositories, counter allocator, and domain services
    url_repository = UrlWriteRepository()
    counter_service = CounterService(
        redis_client=redis_client,
        counter_key=settings.COUNTER_KEY,
        batch_size=settings.COUNTER_BATCH_SIZE,
        start_offset=settings.COUNTER_START_OFFSET,
    )
    url_write_service = UrlWriteService(
        repository=url_repository,
        counter_service=counter_service,
        base_url=settings.BASE_URL,
    )
    rate_limiter = RateLimiter(
        redis_client=redis_client,
        limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
        enabled=settings.RATE_LIMIT_ENABLED,
    )

    # Attach shared dependencies to app.state for FastAPI Dependency Injection
    app.state.url_write_service = url_write_service
    app.state.rate_limiter = rate_limiter
    app.state.counter_service = counter_service
    app.state.redis_client = redis_client

    logger.info("Write Service started successfully.")
    yield

    logger.info("Shutting down Write Service...")
    # Clean up Redis and Database pools
    if redis_client:
        await redis_client.aclose()
    await db_manager.close()
    logger.info("Write Service cleanly stopped.")


def create_app() -> FastAPI:
    """Application factory for Write Service."""
    app = FastAPI(
        title="URL Shortener - Write Service",
        description="Write-heavy microservice responsible for short URL creation and ID allocation.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register structured logging middleware
    app.add_middleware(
        StructuredLoggingMiddleware,
        service_name=settings.SERVICE_NAME,
        logger=logger,
    )

    # Register centralized exception handlers for standard JSON error schemas
    register_exception_handlers(app)

    # Include API routes
    app.include_router(health_router)
    app.include_router(url_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.write_service.app.main:app",
        host="0.0.0.0",
        port=settings.WRITE_SERVICE_PORT,
        reload=False,
    )
