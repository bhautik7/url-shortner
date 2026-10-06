"""
Main Entry Point for Read Service Application.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis
from services.read_service.app.api.health import router as health_router
from services.read_service.app.api.routes import router as redirect_router
from services.read_service.app.core.config import settings
from services.read_service.app.db.session import db_manager
from services.read_service.app.repositories.url_repository import UrlReadRepository
from services.read_service.app.services.cache_service import CacheService
from services.read_service.app.services.redirect_service import RedirectService
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
    logger.info("Initializing Read Service dependencies...")

    # Initialize async Redis client connection pool
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            decode_responses=False,
        )
    except Exception as exc:
        logger.warning(f"Could not connect to Redis at startup: {exc}. Will fallback to DB.")
        redis_client = None

    url_repository = UrlReadRepository()
    cache_service = CacheService(
        redis_client=redis_client,
        key_prefix=settings.CACHE_KEY_PREFIX,
        default_ttl=settings.CACHE_DEFAULT_TTL_SECONDS,
        max_ttl=settings.CACHE_MAX_TTL_SECONDS,
    )
    redirect_service = RedirectService(
        repository=url_repository,
        cache_service=cache_service,
    )

    # Attach to app.state for FastAPI Dependency Injection
    app.state.redirect_service = redirect_service
    app.state.cache_service = cache_service
    app.state.redis_client = redis_client

    logger.info("Read Service started successfully.")
    yield

    logger.info("Shutting down Read Service...")
    if redis_client:
        await redis_client.aclose()
    await db_manager.close()
    logger.info("Read Service cleanly stopped.")


def create_app() -> FastAPI:
    """Application factory for Read Service."""
    app = FastAPI(
        title="URL Shortener - Read Service",
        description="Read-heavy microservice responsible for sub-millisecond URL redirections.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register structured logging middleware
    app.add_middleware(
        StructuredLoggingMiddleware,
        service_name=settings.SERVICE_NAME,
        logger=logger,
    )

    # Register centralized exception handlers
    register_exception_handlers(app)

    # Include API routes
    app.include_router(health_router)
    app.include_router(redirect_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.read_service.app.main:app",
        host="0.0.0.0",
        port=settings.READ_SERVICE_PORT,
        reload=False,
    )
