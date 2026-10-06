"""
Redirect API Endpoints for Read Service.
"""

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from services.read_service.app.db.session import get_db_session
from services.read_service.app.services.redirect_service import RedirectService

router = APIRouter(tags=["Redirect"])


def get_redirect_service(request: Request) -> RedirectService:
    """Dependency injection helper to obtain RedirectService."""
    return request.app.state.redirect_service


@router.get(
    "/{short_code}",
    status_code=status.HTTP_302_FOUND,
    summary="Redirect short code to destination long URL",
    description=(
        "Looks up the short code in Redis cache first (cache hit), falling back to PostgreSQL (cache miss). "
        "Returns HTTP 302 redirect on success, HTTP 410 if expired, or HTTP 404 if not found."
    ),
    responses={
        302: {"description": "Temporary redirect to target URL"},
        404: {"description": "Short code not found"},
        410: {"description": "Short code has expired"},
    },
)
async def redirect_to_long_url(
    short_code: str = Path(..., min_length=1, max_length=30, description="Short code or custom alias"),
    db_session: AsyncSession = Depends(get_db_session),
    redirect_service: RedirectService = Depends(get_redirect_service),
) -> RedirectResponse:
    """
    GET /{short_code} endpoint handler.

    Why HTTP 302 (Found) instead of HTTP 301 (Moved Permanently)?
    - HTTP 301 is aggressively and permanently cached by browsers and downstream ISP proxies.
      If a short link expires or changes, a client with a 301 cache will never hit our servers again.
    - HTTP 302 ensures the browser hits our API Gateway on every access, allowing real-time
      expiration enforcement, analytics tracking, and instant URL updates.
    """
    destination_url = await redirect_service.get_destination_url(
        session=db_session,
        short_code=short_code,
    )

    return RedirectResponse(
        url=destination_url,
        status_code=status.HTTP_302_FOUND,
    )
