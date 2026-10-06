"""
Read Service Configuration Settings.
"""

from pydantic import Field
from shared.config.base import CommonSettings


class ReadServiceSettings(CommonSettings):
    """
    Configuration settings specific to the Read Service.
    """

    SERVICE_NAME: str = "read_service"
    READ_SERVICE_PORT: int = Field(default=8002)

    # Redis Cache Configuration
    CACHE_KEY_PREFIX: str = Field(default="url:")
    CACHE_DEFAULT_TTL_SECONDS: int = Field(
        default=86400,
        description="Default TTL for URLs without expiration (24 hours)",
    )
    CACHE_MAX_TTL_SECONDS: int = Field(
        default=604800,
        description="Maximum TTL cap for cached items (7 days)",
    )


settings = ReadServiceSettings()
