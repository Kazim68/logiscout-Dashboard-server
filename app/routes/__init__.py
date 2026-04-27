"""
Routes module initialization.
Exports all route routers.
"""

from app.routes.auth_routes import router as auth_router
from app.routes.google_oauth_routes import router as google_oauth_router
from app.routes.github_oauth_routes import router as github_oauth_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.project_routes import router as project_router
from app.routes.live_log_routes import router as live_log_router

__all__ = [
    "auth_router",
    "google_oauth_router",
    "github_oauth_router",
    "dashboard_router",
    "project_router",
    "live_log_router",
]
