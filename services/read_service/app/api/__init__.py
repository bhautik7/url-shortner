"""API package for read service."""

from services.read_service.app.api.health import router as health_router
from services.read_service.app.api.routes import router as redirect_router

__all__ = ["health_router", "redirect_router"]
