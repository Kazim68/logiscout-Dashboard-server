"""
Schemas module initialization.
Exports all schema classes.
"""

from app.schemas.user_schema import (
    UserSignUpRequest,
    UserSignInRequest,
    UserResponse,
    AuthResponse,
    DashboardStats,
    DashboardResponse,
    OAuthRedirectResponse,
    OAuthCallbackRequest
)

__all__ = [
    "UserSignUpRequest",
    "UserSignInRequest",
    "UserResponse",
    "AuthResponse",
    "DashboardStats",
    "DashboardResponse",
    "OAuthRedirectResponse",
    "OAuthCallbackRequest"
]
