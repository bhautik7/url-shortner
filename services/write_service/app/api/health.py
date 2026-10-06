"""
Health and Readiness Probes for Write Service.
"""

from fastapi import APIRouter, Depends, Response, status
import redis.asyncio as redis
from services.write_service.app.db.session import db_manager

router = APIRouter(tags=["Health"])


async def check_redis_connection(redis_client: redis.Redis) -> bool:
    """Checks if Redis is reachable."""
    try:
        return await redis_client.ping() is True
    except Exception:
        return False


@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """
    Liveness probe: verifies that the application process is running and responding.
    """
    return {"status": "ok", "service": "write_service"}


@router.get("/ready")
async def readiness_probe(
    response: Response,
) -> dict:
    """
    Readiness probe: verifies that all critical dependencies (PostgreSQL and Redis)
    are reachable before routing traffic to this instance.
    """
    from services.write_service.app.main import redis_client

    db_ok = await db_manager.ping()
    redis_ok = await check_redis_connection(redis_client) if redis_client else False

    is_ready = db_ok and redis_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "connected" if db_ok else "unreachable",
            "redis": "connected" if redis_ok else "unreachable",
        }

    return {
        "status": "ready",
        "service": "write_service",
        "database": "connected",
        "redis": "connected",
    }
