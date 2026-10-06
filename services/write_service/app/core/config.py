"""
Write Service Configuration Settings.
"""

from pydantic import Field
from shared.config.base import CommonSettings


class WriteServiceSettings(CommonSettings):
    """
    Configuration settings specific to the Write Service.
    """

    SERVICE_NAME: str = "write_service"
    WRITE_SERVICE_PORT: int = Field(default=8001)

    # Counter Batching
    COUNTER_KEY: str = Field(default="url_shortener:global_counter")
    COUNTER_START_OFFSET: int = Field(
        default=1000000,
        description="Initial counter offset to guarantee short codes have at least ~4 characters",
    )
    COUNTER_BATCH_SIZE: int = Field(
        default=1000,
        description="Number of IDs leased in each atomic Redis INCRBY operation",
    )

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_PER_MINUTE: int = Field(default=100)


settings = WriteServiceSettings()
