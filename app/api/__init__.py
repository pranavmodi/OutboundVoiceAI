"""API routes for dashboard and WebSocket."""
from .dashboard import router as dashboard_router
from .websocket import router as websocket_router
from .settings import router as settings_router

__all__ = ["dashboard_router", "websocket_router", "settings_router"]
