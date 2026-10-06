"""Shared utilities package."""

from shared.utilities.base62 import decode_base62, encode_base62
from shared.utilities.errors import (
    AppException,
    ConflictError,
    DependencyUnavailableError,
    ErrorDetail,
    ErrorResponse,
    ExpiredError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    register_exception_handlers,
)
from shared.utilities.logging import StructuredJsonFormatter, StructuredLoggingMiddleware, setup_logger
from shared.utilities.validation import (
    validate_custom_alias,
    validate_expiration_date,
    validate_long_url,
)

__all__ = [
    "encode_base62",
    "decode_base62",
    "AppException",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "ExpiredError",
    "RateLimitError",
    "DependencyUnavailableError",
    "InternalServerError",
    "ErrorDetail",
    "ErrorResponse",
    "register_exception_handlers",
    "StructuredJsonFormatter",
    "StructuredLoggingMiddleware",
    "setup_logger",
    "validate_long_url",
    "validate_custom_alias",
    "validate_expiration_date",
]
