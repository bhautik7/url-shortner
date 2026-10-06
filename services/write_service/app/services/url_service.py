"""
URL Business Logic Service for Write Service.

Coordinates validation, ID generation, Base62 encoding, and persistence.
"""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from services.write_service.app.repositories.url_repository import UrlWriteRepository
from services.write_service.app.schemas.url import CreateUrlRequest, CreateUrlResponse
from services.write_service.app.services.counter_service import CounterService
from shared.utilities.base62 import encode_base62
from shared.utilities.errors import ConflictError

logger = logging.getLogger("write_service")


class UrlWriteService:
    """
    Orchestrates URL creation business logic.
    """

    def __init__(
        self,
        repository: UrlWriteRepository,
        counter_service: CounterService,
        base_url: str = "http://localhost",
    ):
        self.repository = repository
        self.counter_service = counter_service
        self.base_url = base_url.rstrip("/")

    async def create_short_url(
        self,
        session: AsyncSession,
        request: CreateUrlRequest,
        created_by: Optional[str] = None,
    ) -> CreateUrlResponse:
        """
        Creates a new short URL or registers a custom alias.

        Flow:
        1. If custom_alias is provided:
           - Check if alias is already registered in DB.
           - If found, raise 409 Conflict immediately.
           - Use custom_alias as the unique short_code.
        2. If no custom_alias:
           - Request the next unique monotonic integer from the in-memory counter batch.
           - Convert integer to deterministic Base62 string (e.g., 1000001 -> '4C92x').
           - Set short_code = base62_string.
        3. Persist URL entity to PostgreSQL.
        4. Return response schema with full short URL.
        """
        if request.custom_alias:
            # Check for existing custom alias
            existing = await self.repository.get_by_short_code(session, request.custom_alias)
            if existing:
                logger.warning(
                    f"Conflict: Custom alias '{request.custom_alias}' already in use",
                    extra={"custom_alias": request.custom_alias},
                )
                raise ConflictError("The requested alias is already in use.")

            short_code = request.custom_alias
            alias_val = request.custom_alias
        else:
            # We fetch a unique monotonic counter from the Redis-backed batch allocator
            counter_id = await self.counter_service.get_next_id()
            short_code = encode_base62(counter_id)
            alias_val = None

        # Persist to PostgreSQL database
        saved_url = await self.repository.save_url(
            session=session,
            short_code=short_code,
            long_url=request.long_url,
            expires_at=request.expiration_date,
            custom_alias=alias_val,
            created_by=created_by,
        )

        full_short_url = f"{self.base_url}/{saved_url.short_code}"

        logger.info(
            f"Created short URL: {full_short_url} -> {saved_url.long_url}",
            extra={
                "short_code": saved_url.short_code,
                "is_custom_alias": bool(request.custom_alias),
                "expires_at": str(saved_url.expires_at) if saved_url.expires_at else None,
            },
        )

        return CreateUrlResponse(
            short_code=saved_url.short_code,
            short_url=full_short_url,
            long_url=saved_url.long_url,
            expiration_date=saved_url.expires_at,
        )
