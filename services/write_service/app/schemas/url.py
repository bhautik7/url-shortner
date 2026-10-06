"""
Pydantic Schemas for URL Creation Request and Response.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shared.utilities.validation import validate_custom_alias, validate_expiration_date, validate_long_url


class CreateUrlRequest(BaseModel):
    """
    Payload for creating a new shortened URL.
    """

    long_url: str = Field(
        ...,
        description="The target URL to shorten (HTTP or HTTPS)",
        examples=["https://example.com/some/very/long/url"],
    )
    custom_alias: Optional[str] = Field(
        default=None,
        description="Optional custom alias (4-30 chars, alphanumeric + '-' and '_')",
        examples=["my-custom-link"],
    )
    expiration_date: Optional[datetime] = Field(
        default=None,
        description="Optional ISO 8601 UTC timestamp when this link expires",
        examples=["2026-12-31T23:59:59Z"],
    )

    @field_validator("long_url")
    @classmethod
    def check_long_url(cls, v: str) -> str:
        return validate_long_url(v)

    @field_validator("custom_alias")
    @classmethod
    def check_custom_alias(cls, v: Optional[str]) -> Optional[str]:
        return validate_custom_alias(v)

    @field_validator("expiration_date")
    @classmethod
    def check_expiration_date(cls, v: Optional[datetime]) -> Optional[datetime]:
        return validate_expiration_date(v)


class CreateUrlResponse(BaseModel):
    """
    Response returned upon successful URL shortening.
    """

    model_config = ConfigDict(from_attributes=True)

    short_code: str = Field(..., description="Unique generated code or custom alias")
    short_url: str = Field(..., description="Full redirectable short URL")
    long_url: str = Field(..., description="Destination target URL")
    expiration_date: Optional[datetime] = Field(
        default=None,
        description="Expiration timestamp if specified",
    )
