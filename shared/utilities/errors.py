"""
Centralized Error Handling, Error Schemas, and Exception Hierarchy.

All application errors return a uniform JSON format:
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable description"
  }
}
"""

from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Base & Domain Exceptions
# ---------------------------------------------------------------------------


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Optional[dict[str, str]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


class ValidationError(AppException):
    """HTTP 400 Validation Error."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
            message=message,
        )


class NotFoundError(AppException):
    """HTTP 404 URL Not Found."""

    def __init__(self, message: str = "The requested short URL was not found.", code: str = "URL_NOT_FOUND"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            message=message,
        )


class ConflictError(AppException):
    """HTTP 409 Conflict (e.g. Custom Alias already taken)."""

    def __init__(self, message: str = "The requested alias is already in use.", code: str = "ALIAS_ALREADY_EXISTS"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            message=message,
        )


class ExpiredError(AppException):
    """HTTP 410 URL Expired (Gone)."""

    def __init__(self, message: str = "The requested short URL has expired.", code: str = "URL_EXPIRED"):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            code=code,
            message=message,
        )


class RateLimitError(AppException):
    """HTTP 429 Too Many Requests."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: int = 60,
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=code,
            message=message,
            headers={"Retry-After": str(retry_after)},
        )


class DependencyUnavailableError(AppException):
    """HTTP 503 Dependency Unavailable (e.g., Redis counter down during write)."""

    def __init__(
        self,
        message: str = "Required dependency service is temporarily unavailable.",
        code: str = "DEPENDENCY_UNAVAILABLE",
    ):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            message=message,
        )


class InternalServerError(AppException):
    """HTTP 500 Internal Server Error."""

    def __init__(
        self,
        message: str = "An unexpected error occurred. Please try again later.",
        code: str = "INTERNAL_SERVER_ERROR",
    ):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=code,
            message=message,
        )


# ---------------------------------------------------------------------------
# FastAPI Exception Handler Registration
# ---------------------------------------------------------------------------


def create_error_response(status_code: int, code: str, message: str, headers: Optional[dict[str, str]] = None) -> JSONResponse:
    """Helper to generate standardized JSON responses."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers centralized exception handlers for FastAPI.
    Ensures that uncaught exceptions and standard validation errors match
    the uniform JSON error response specification.
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return create_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Extract readable message from Pydantic validation errors
        errors = exc.errors()
        messages = []
        for err in errors:
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", "Invalid value")
            messages.append(f"{loc}: {msg}" if loc else msg)
        combined_message = "; ".join(messages) if messages else "Invalid request parameters."
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message=combined_message,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
            status.HTTP_503_SERVICE_UNAVAILABLE: "DEPENDENCY_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        detail_msg = exc.detail if isinstance(exc.detail, str) else "An HTTP error occurred."
        return create_error_response(
            status_code=exc.status_code,
            code=code,
            message=detail_msg,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Mask internal error details from the client to prevent sensitive data leakage
        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
        )
