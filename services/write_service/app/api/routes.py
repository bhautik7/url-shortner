"""
URL Creation API Endpoints for Write Service.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from services.write_service.app.core.rate_limiter import RateLimiter
from services.write_service.app.db.session import get_db_session
from services.write_service.app.schemas.url import CreateUrlRequest, CreateUrlResponse
from services.write_service.app.services.url_service import UrlWriteService

router = APIRouter(prefix="/api/v1/urls", tags=["URLs"])


def get_url_write_service(request: Request) -> UrlWriteService:
    """Dependency injection helper to obtain UrlWriteService."""
    return request.app.state.url_write_service


def get_rate_limiter(request: Request) -> RateLimiter:
    """Dependency injection helper to obtain RateLimiter."""
    return request.app.state.rate_limiter


@router.post(
    "",
    response_model=CreateUrlResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a shortened URL or custom alias",
    description=(
        "Accepts a destination long URL with an optional custom alias and expiration date. "
        "Returns the newly generated short code and full short URL."
    ),
)
async def create_url(
    payload: CreateUrlRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    url_service: UrlWriteService = Depends(get_url_write_service),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> CreateUrlResponse:
    """
    POST /api/v1/urls endpoint handler.
    """
    # Enforce Redis-backed rate limiting per client IP
    await rate_limiter.check_rate_limit(request)

    # Client identifier for logging/audit
    client_ip = request.headers.get("X-Forwarded-For") or (
        request.client.host if request.client else None
    )

    response = await url_service.create_short_url(
        session=db_session,
        request=payload,
        created_by=client_ip,
    )

    return response
