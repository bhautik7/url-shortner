"""
Health and Readiness Probes for Read Service.
"""

from fastapi import APIRouter, Response, status
import redis.asyncio as redis
from services.read_service.app.db.session import db_manager

router = APIRouter(tags=["Health"])


async def check_redis_connection(redis_client: redis.Redis) -> bool:
    """Checks if Redis cache is reachable."""
    if redis_client is None:
        return False
    try:
        return await redis_client.ping() is True
    except Exception:
        return False


@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """
    Liveness probe: verifies that the application process is running and responsive.
    """
    return {"status": "ok", "service": "read_service"}


@router.get("/ready")
async def readiness_probe(response: Response) -> dict:
    """
    Readiness probe: verifies PostgreSQL connectivity.
    Note: Read service is designed to function even if Redis is degraded (fallback to DB).
    """
    from services.read_service.app.main import redis_client

    db_ok = await db_manager.ping()
    redis_ok = await check_redis_connection(redis_client) if redis_client else False

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "unreachable",
            "redis": "connected" if redis_ok else "unreachable",
        }

    return {
        "status": "ready",
        "service": "read_service",
        "database": "connected",
        "redis": "connected" if redis_ok else "degraded",
    }
