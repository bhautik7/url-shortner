"""
Structured Logging and Request Context Tracking.

Provides:
- JSON/structured log formatters
- Request ID extraction and propagation
- Request duration metrics
"""

import json
import logging
import sys
import time
import uuid
from typing import Any, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects for log aggregators (e.g. Loki, ELK, Datadog).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom extra fields if attached to the record
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "module",
                "msecs", "message", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName"
            ):
                log_obj[key] = val

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logger(service_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Configures and returns a structured logger for the specified service.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    return logger


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches X-Request-ID and logs every incoming HTTP request and response
    with status code, duration in milliseconds, client IP, method, and path.
    """

    def __init__(self, app: Any, service_name: str, logger: logging.Logger):
        super().__init__(app)
        self.service_name = service_name
        self.logger = logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract existing X-Request-ID header or generate a new UUID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Attach request_id to request state so downstream handlers can access it
        request.state.request_id = request_id

        start_time = time.perf_counter()
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self.logger.error(
                "Request failed with unhandled exception",
                extra={
                    "service": self.service_name,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise exc

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        
        # Propagate X-Request-ID back in response headers for tracing
        response.headers["X-Request-ID"] = request_id

        # Skip verbose access logging for frequent health checks to avoid noise
        if request.url.path not in ("/health", "/ready"):
            self.logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
                extra={
                    "service": self.service_name,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

        return response
