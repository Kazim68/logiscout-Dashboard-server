"""
Dashboard Routes
Protected routes that require JWT authentication.
"""

from fastapi import APIRouter, Depends

from app.dependencies.auth_dependency import get_current_user
from app.utils.response_handler import create_response
from app.core.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(
    prefix="/api",
    tags=["Dashboard"]
)


@router.get(
    "/dashboard",
    summary="Get dashboard data",
    description="Get user information and dashboard statistics. Requires authentication."
)
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    """
    Get dashboard data for authenticated user.
    
    Returns:
    - User information
    - Dashboard statistics (dummy data for now)
    
    Requires: JWT Bearer token in Authorization header
    """
    # Dummy dashboard statistics
    # In production, these would come from actual data
    dashboard_stats = {
        "total_logs": 15420,
        "active_incidents": 3,
        "resolved_today": 12,
        "avg_resolution_time": "4m 32s",
        "logs_by_level": {
            "info": 10500,
            "warning": 3200,
            "error": 1520,
            "critical": 200
        },
        "recent_incidents": [
            {
                "id": "INC-001",
                "title": "Database connection timeout",
                "status": "investigating",
                "severity": "high",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "id": "INC-002",
                "title": "API rate limit exceeded",
                "status": "monitoring",
                "severity": "medium",
                "created_at": "2024-01-15T09:15:00Z"
            },
            {
                "id": "INC-003",
                "title": "Memory usage spike",
                "status": "resolved",
                "severity": "low",
                "created_at": "2024-01-15T08:00:00Z"
            }
        ],
        "system_health": {
            "api_server": "healthy",
            "database": "healthy",
            "cache": "healthy",
            "queue": "degraded"
        }
    }
    
    return create_response(
        success=True,
        message="Dashboard data retrieved successfully",
        data={
            "user": current_user,
            "stats": dashboard_stats
        }
    )


@router.get(
    "/profile",
    summary="Get user profile",
    description="Get detailed user profile information. Requires authentication."
)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Get user profile information.
    
    Returns detailed user information for the authenticated user.
    
    Requires: JWT Bearer token in Authorization header
    """
    return create_response(
        success=True,
        message="Profile retrieved successfully",
        data=current_user
    )


@router.get(
    "/health",
    summary="Health check",
    description="Check if the API is running."
)
async def health_check():
    """
    Health check endpoint.
    
    Returns API health status. Does not require authentication.
    """
    return create_response(
        success=True,
        message="API is healthy",
        data={
            "status": "healthy",
            "version": "1.0.0"
        }
    )
