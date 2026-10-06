"""
Integration Test Fixtures: In-memory async database and Redis fixtures.
"""

from collections.abc import AsyncGenerator, AsyncIterator
import os
import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from services.read_service.app.api.health import router as read_health_router
from services.read_service.app.api.routes import router as read_url_router
from services.read_service.app.db.session import get_db_session as get_read_db_session
from services.read_service.app.repositories.url_repository import UrlReadRepository
from services.read_service.app.services.cache_service import CacheService
from services.read_service.app.services.redirect_service import RedirectService
from services.write_service.app.api.health import router as write_health_router
from services.write_service.app.api.routes import router as write_url_router
from services.write_service.app.core.rate_limiter import RateLimiter
from services.write_service.app.db.session import get_db_session as get_write_db_session
from services.write_service.app.repositories.url_repository import UrlWriteRepository
from services.write_service.app.services.counter_service import CounterService
from services.write_service.app.services.url_service import UrlWriteService
from shared.database.base import Base
from shared.utilities.errors import register_exception_handlers

TEST_DB_PATH = "/tmp/test_url_shortener.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"


@pytest.fixture
async def db_session_factory():
    """Creates file-backed SQLite database for integration tests and yields session factory."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
async def fake_redis():
    """Provides an isolated in-memory async Redis instance."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def write_app(db_session_factory, fake_redis):
    """Creates a configured Write Service FastAPI application for testing."""
    app = FastAPI(title="Test Write Service")
    register_exception_handlers(app)

    url_repo = UrlWriteRepository()
    counter_service = CounterService(
        redis_client=fake_redis,
        counter_key="test:global_counter",
        batch_size=10,
        start_offset=1000000,
    )
    url_write_service = UrlWriteService(
        repository=url_repo,
        counter_service=counter_service,
        base_url="http://localhost",
    )
    rate_limiter = RateLimiter(
        redis_client=fake_redis,
        limit_per_minute=100,
        enabled=True,
    )

    app.state.url_write_service = url_write_service
    app.state.counter_service = counter_service
    app.state.rate_limiter = rate_limiter
    app.state.redis_client = fake_redis

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_write_db_session] = override_get_db
    app.include_router(write_health_router)
    app.include_router(write_url_router)

    return app


@pytest.fixture
def read_app(db_session_factory, fake_redis):
    """Creates a configured Read Service FastAPI application for testing."""
    app = FastAPI(title="Test Read Service")
    register_exception_handlers(app)

    url_repo = UrlReadRepository()
    cache_service = CacheService(
        redis_client=fake_redis,
        key_prefix="url:",
        default_ttl=86400,
        max_ttl=604800,
    )
    redirect_service = RedirectService(
        repository=url_repo,
        cache_service=cache_service,
    )

    app.state.redirect_service = redirect_service
    app.state.cache_service = cache_service
    app.state.redis_client = fake_redis

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_read_db_session] = override_get_db
    app.include_router(read_health_router)
    app.include_router(read_url_router)

    return app


@pytest.fixture
async def write_client(write_app) -> AsyncIterator[AsyncClient]:
    """HTTP client for Write Service."""
    transport = ASGITransport(app=write_app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.fixture
async def read_client(read_app) -> AsyncIterator[AsyncClient]:
    """HTTP client for Read Service."""
    transport = ASGITransport(app=read_app)
    async with AsyncClient(transport=transport, base_url="http://localhost", follow_redirects=False) as client:
        yield client
